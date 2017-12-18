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


def parse_int(text: str, context: Optional[SymbolTable], filename: str, line: int, *,
              column: int=1, minimum: int=0, maximum: int=0xffff) -> int:
    src = SourceLine(text, filename, line, column)
    node = parse_expression(src, context)
    if isinstance(node.body, ast.Name) and node.body.id in ("true", "false"):
        node.body = ast.Num(1 if node.body.id == "true" else 0)  # convert boolean to int
    if isinstance(node.body, ast.Num):
        num = node.body.n
        if isinstance(num, int):
            if minimum <= num <= maximum:
                return num
            raise src.to_error("int too large")
        raise src.to_error("int expected")
    raise src.to_error("int expected, not " + type(node.body).__name__)


def parse_number(text: str, context: Optional[SymbolTable], filename: str, line: int, *,
                 column: int=1, minimum: float=FLOAT_MAX_NEGATIVE, maximum: float=FLOAT_MAX_POSITIVE) -> Union[int, float]:
    src = SourceLine(text, filename, line, column)
    node = parse_expression(src, context)
    if isinstance(node.body, ast.Name) and node.body.id in ("true", "false"):
        node.body = ast.Num(1 if node.body.id == "true" else 0)  # convert boolean to number
    if isinstance(node.body, ast.Num):
        num = node.body.n
        if isinstance(num, (int, float)):
            if minimum <= num <= maximum:
                return num
            raise src.to_error("number too large")
        raise src.to_error("int or float expected")
    # print("ast error, node: ", ast.dump(node))
    raise src.to_error("int or float expected, not " + type(node.body).__name__)


def parse_string(text: str, context: Optional[SymbolTable], filename: str, line: int, *, column: int=1) -> str:
    src = SourceLine(text, filename, line, column)
    node = parse_expression(src, context)
    if isinstance(node.body, ast.Str):
        return node.body.s
    # print("ast error, node: ", ast.dump(node))
    raise src.to_error("string expected, not " + type(node.body).__name__)


def parse_primitive(text: str, context: Optional[SymbolTable], filename: str, line: int, *,
                    column: int=1, minimum: float = FLOAT_MAX_NEGATIVE, maximum: float = FLOAT_MAX_POSITIVE) -> Union[int, float, str]:
    src = SourceLine(text, filename, line, column)
    node = parse_expression(src, context)
    if isinstance(node.body, ast.Str):
        return node.body.s
    if isinstance(node.body, ast.Name) and node.body.id in ("true", "false"):
        node.body = ast.Num(1 if node.body.id == "true" else 0)  # convert boolean to int
    if isinstance(node.body, ast.Num):
        num = node.body.n
        if isinstance(num, (int, float)):
            if minimum <= num <= maximum:
                return num
            raise src.to_error("number too large")
        raise src.to_error("int or float or string expected")
    # print("ast error, node: ", ast.dump(node))
    raise src.to_error("int or float or string expected, not " + type(node.body).__name__)


def parse_expression(src: SourceLine, context: Optional[SymbolTable]) -> ast.Expression:
    text = src.preprocess()
    node = ast.parse(text, src.filename, mode="eval")
    if isinstance(node, ast.Expression):
        node = ExpressionTransformer(src, context).visit(node)
        return node
    # print("ast error, node: ", ast.dump(node))
    raise src.to_error("expression expected, not " + type(node.body).__name__)


class EvaluatingTransformer(ast.NodeTransformer):
    def __init__(self, src: SourceLine, context: SymbolTable) -> None:
        super().__init__()
        self.src = src
        self.context = context

    def error(self, message: str, column: int=0) -> ParseError:
        return ParseError(message, self.src.text, self.src.filename, self.src.line, column or self.src.column)


class ExpressionTransformer(EvaluatingTransformer):
    def _dotted_name_from_attr(self, node: ast.Attribute) -> str:
        if isinstance(node.value, ast.Name):
            return node.value.id + '.' + node.attr
        if isinstance(node.value, ast.Attribute):
            return self._dotted_name_from_attr(node.value) + '.' + node.attr
        raise self.error("dotted name error")

    def visit_Attribute(self, node: ast.Attribute):
        dotted_name = self._dotted_name_from_attr(node)
        scope, symbol = self.context.lookup(dotted_name)
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

        expression = ast.copy_location(ast.Expression(node), node)
        code = compile(expression, self.src.filename, mode="eval")
        if self.context:
            globals = self.context.as_eval_dict()
        else:
            globals = {"__builtins__": {}}
        try:
            result = eval(code, globals, {})
        except Exception as x:
            raise self.src.to_error(str(x))
        if type(result) in (int, float):
            return ast.copy_location(ast.Num(result), node)
        if type(result) is str:
            return ast.copy_location(ast.Str(result), node)
        raise self.error("cannot evaluate expression")


if __name__ == "__main__":
    src = SourceLine("2+#derp", "<source>", 1, 0)
    symbols = SymbolTable("<root>", None, None)
    symbols.define_variable("derp", "<source>", 1, DataType.BYTE, address=2345)
    e = parse_expression(src, symbols)
    print("EXPRESSION:", e)
    import astunparse
    print(astunparse.unparse(e))
