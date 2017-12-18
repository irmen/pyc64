"""
Intermediate Language for 6502/6510 microprocessors
This is the expression parser/evaluator.

Written by Irmen de Jong (irmen@razorvine.net)
License: GNU GPL 3.0, see LICENSE
"""

import ast
from symbols import FLOAT_MAX_POSITIVE, FLOAT_MAX_NEGATIVE, SymbolTable, SymbolError, \
    VariableDef, ConstantDef, DataType, STRING_DATATYPES
from typing import Union, Optional


class ParseError(Exception):
    def __init__(self, message: str, text: str, sourcefile: str, line: int, column: int=1) -> None:
        self.filename = sourcefile
        self.msg = message
        self.lineno = line
        self.offset = column
        self.text = text

    def __str__(self):
        if self.offset:
            return "{:s}:{:d}:{:d} {:s}".format(self.filename, self.lineno, self.offset, self.msg)
        else:
            return "{:s}:{:d}: {:s}".format(self.filename, self.lineno, self.msg)


class SourceLine:
    def __init__(self, text: str, filename: str, line: int, column: int=0) -> None:
        self.filename = filename
        self.text = text.strip()
        self.line = line
        self.column = column

    def to_error(self, message: str) -> ParseError:
        return ParseError(message, self.text, self.filename, self.line, self.column)

    def preprocess(self) -> str:
        # transforms the source text into valid Python syntax by bending some things, so ast can parse it.
        # $d020      ->  0xd020
        # %101001    ->  0xb101001
        # #something ->  __ptr@something   (matmult operator)
        text = ""
        quotes_stack = ""
        characters = enumerate(self.text + " ")
        for i, c in characters:
            if c in ("'", '"'):
                if quotes_stack and quotes_stack[-1] == c:
                    quotes_stack = quotes_stack[:-1]
                else:
                    quotes_stack += c
                text += c
                continue
            if not quotes_stack:
                if c == '%' and self.text[i + 1] in "01":
                    text += "0b"
                    continue
                if c == '$' and self.text[i + 1] in "0123456789abcdefABCDEF":
                    text += "0x"
                    continue
                if c == '#':
                    if i > 0:
                        text += " "
                    text += "__ptr@"
                    continue
            text += c
        return text


def parse_expr_as_int(text: str, context: Optional[SymbolTable], filename: str, line: int, *,
                      column: int=1, minimum: int=0, maximum: int=0xffff) -> int:
    src = SourceLine(text, filename, line, column)
    result = parse_constant_expression(src, context)
    if isinstance(result, bool):
        return int(result)
    if isinstance(result, int):
        if minimum <= result <= maximum:
            return result
    raise src.to_error("int expected, not " + type(result).__name__)


def parse_expr_as_number(text: str, context: Optional[SymbolTable], filename: str, line: int, *,
                         column: int=1, minimum: float=FLOAT_MAX_NEGATIVE, maximum: float=FLOAT_MAX_POSITIVE) -> Union[int, float]:
    src = SourceLine(text, filename, line, column)
    result = parse_constant_expression(src, context)
    if isinstance(result, bool):
        return int(result)
    if isinstance(result, (int, float)):
        if minimum <= result <= maximum:
            return result
        raise src.to_error("number too large")
    raise src.to_error("int or float expected, not " + type(result).__name__)


def parse_expr_as_string(text: str, context: Optional[SymbolTable], filename: str, line: int, *, column: int=1) -> str:
    src = SourceLine(text, filename, line, column)
    result = parse_constant_expression(src, context)
    if isinstance(result, str):
        return result
    raise src.to_error("string expected, not " + type(result).__name__)


def parse_expr_as_primitive(text: str, context: Optional[SymbolTable], filename: str, line: int, *,
                            column: int=1, minimum: float = FLOAT_MAX_NEGATIVE,
                            maximum: float = FLOAT_MAX_POSITIVE) -> Union[int, float, str]:
    src = SourceLine(text, filename, line, column)
    result = parse_constant_expression(src, context)
    if isinstance(result, bool):
        return int(result)
    if isinstance(result, (int, float)):
        if minimum <= result <= maximum:
            return result
        raise src.to_error("number too large")
    if isinstance(result, str):
        return result
    raise src.to_error("int or float or string expected, not " + type(result).__name__)


def parse_constant_expression(src: SourceLine, context: Optional[SymbolTable]) -> Union[int, float, str]:
    text = src.preprocess()
    try:
        node = ast.parse(text, src.filename, mode="eval")
    except SyntaxError as x:
        raise src.to_error(str(x))
    # if isinstance(node, ast.Expression):
    if isinstance(node, ast.Expression):
        result = ExpressionTransformer(src, context).evaluate(node)
        return result
    else:
        raise TypeError("ast.Expression expected")


class EvaluatingTransformer(ast.NodeTransformer):
    def __init__(self, src: SourceLine, context: SymbolTable) -> None:
        super().__init__()
        self.src = src
        self.context = context

    def error(self, message: str, column: int=0) -> ParseError:
        return ParseError(message, self.src.text, self.src.filename, self.src.line, column or self.src.column)

    def evaluate(self, node: ast.Expression) -> Union[int, float, str, bool]:
        node = self.visit(node)
        code = compile(node, self.src.filename, mode="eval")
        if self.context:
            globals = self.context.as_eval_dict()
        else:
            globals = {"__builtins__": {}}
        try:
            return eval(code, globals, {})
        except Exception as x:
            raise self.src.to_error(str(x))


class ExpressionTransformer(EvaluatingTransformer):
    def _dotted_name_from_attr(self, node: ast.Attribute) -> str:
        if isinstance(node.value, ast.Name):
            return node.value.id + '.' + node.attr
        if isinstance(node.value, ast.Attribute):
            return self._dotted_name_from_attr(node.value) + '.' + node.attr
        raise self.error("dotted name error")

    def visit_Name(self, node: ast.Name):
        # convert true/false names to True/False constants
        if node.id == "true":
            return ast.copy_location(ast.NameConstant(True), node)
        if node.id == "false":
            return ast.copy_location(ast.NameConstant(False), node)
        return node

    def visit_Attribute(self, node: ast.Attribute):
        dotted_name = self._dotted_name_from_attr(node)
        try:
            scope, symbol = self.context.lookup(dotted_name)
        except SymbolError as x:
            raise self.error(str(x))
        if isinstance(symbol, ConstantDef):
            if symbol.type in (DataType.BYTE, DataType.WORD, DataType.FLOAT):
                return ast.copy_location(ast.Num(symbol.value), node)
            elif symbol.type in STRING_DATATYPES:
                return ast.copy_location(ast.Str(symbol.value), node)
            else:
                raise self.error("primitive type (byte, word, float, str) required")
        elif isinstance(symbol, VariableDef):
            return ast.copy_location(ast.Name(dotted_name, ast.Load()), node)
        else:
            raise self.error("expected var or const")

    def visit_UnaryOp(self, node):
        if isinstance(node.operand, ast.Num):
            if isinstance(node.op, ast.USub):
                node = self.generic_visit(node)
                return ast.copy_location(ast.Num(-node.operand.n), node)
            if isinstance(node.op, ast.UAdd):
                node = self.generic_visit(node)
                return ast.copy_location(ast.Num(node.operand.n), node)
            raise self.error("expected unary + or -")
        else:
            raise self.error("expected numeric operand for unary operator")

    def visit_BinOp(self, node):
        node = self.generic_visit(node)
        if isinstance(node.op, ast.MatMult):
            if isinstance(node.left, ast.Name) and node.left.id == "__ptr":
                if isinstance(node.right, ast.Name):
                    try:
                        address = self.context.get_address(node.right.id)
                    except SymbolError as x:
                        raise self.error(str(x))
                    else:
                        return ast.copy_location(ast.Num(address), node)
                else:
                    raise self.error("can only take address of a named variable")
            else:
                raise self.error("invalid MatMult/Pointer node in AST")
        return node


if __name__ == "__main__":
    src = SourceLine("2+#derp", "<source>", 1, 0)
    symbols = SymbolTable("<root>", None, None)
    symbols.define_variable("derp", "<source>", 1, DataType.BYTE, address=2345)
    e = parse_constant_expression(src, symbols)
    print("EXPRESSION RESULT:", e)
