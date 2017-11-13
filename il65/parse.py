import re
import os
import ast
import enum
from typing import Set, List, Tuple, Optional, Union, Any
from symbols import SymbolTable, Zeropage, VariableType, Identifier, \
    SubroutineIdentifier, VariableIdentifier, SymbolError, STRING_VARTYPES


REGISTER_SYMBOLS = {"A", "X", "Y", "AX", "AY", "XY", "SC"}


class ParseError(Exception):
    def __init__(self, sourcefile: str, num: int, line: str, message: str) -> None:
        super().__init__(message)
        self.sourcefile = sourcefile
        self.line_num = num
        self.sourceline = line

    def __str__(self):
        return "{:s}:{:d}: {:s}".format(self.sourcefile, self.line_num, self.args[0])


class ProgramFormat(enum.Enum):
    PRG = "prg"
    RAW = "raw"


class ParseResult:
    class Block:
        def __init__(self, sourcefile: str, linenum: int, zeropage: Zeropage) -> None:
            self.sourcefile = sourcefile
            self.linenum = linenum
            self.address = 0
            self.name = ""
            self.statements = []    # type: List[ParseResult._Stmt]
            self.symbols = SymbolTable(zeropage)        # labels, vars, subroutine defs

        @property
        def label_names(self) -> Set[str]:
            return {symbol.name for symbol in self.symbols.iter_labels()}

    class Value:
        def __init__(self, vtype: VariableType, name: str=None) -> None:
            self.vtype = vtype
            self.name = name

        def assignable_from(self, other: 'ParseResult.Value') -> bool:
            return False

    class PlaceholderSymbol(Value):
        def assignable_from(self, other: 'ParseResult.Value') -> bool:
            return True

        def __str__(self):
            return "<Placeholder unresolved {:s}>".format(self.name)

    class ConstantValue(Value):
        # 'immediate' constant value
        def __init__(self, value: int, name: str=None) -> None:
            if 0 <= value < 0x100:
                super().__init__(VariableType.BYTE, name)
            elif value < 0x10000:
                super().__init__(VariableType.WORD, name)
            else:
                raise OverflowError("value too big: ${:x}".format(value))
            self.value = value

        def __hash__(self):
            return hash((self.vtype, self.value, self.name))

        def __eq__(self, other: Any) -> bool:
            if not isinstance(other, ParseResult.ConstantValue):
                return NotImplemented
            elif self is other:
                return True
            else:
                return other.vtype == self.vtype and other.value == self.value and other.name == self.name

        def __str__(self):
            return "<ConstantValue {:d} name={}>".format(self.value, self.name)

    class StringValue(Value):
        # string value
        def __init__(self, value: str, name: str=None) -> None:
            super().__init__(VariableType.STRING, name)
            self.value = value

        def __hash__(self):
            return hash(self.value)

        def __eq__(self, other: Any) -> bool:
            if not isinstance(other, ParseResult.StringValue):
                return NotImplemented
            elif self is other:
                return True
            else:
                return other.vtype == self.vtype and other.value == self.value and other.name == self.name

        def __str__(self):
            return "<StringValue {!r:s} name={}>".format(self.value, self.name)

    class CharValue(Value):
        # character value (1 single character)
        def __init__(self, value: str, name: str=None) -> None:
            super().__init__(VariableType.CHARACTER, name)
            self.value = value

        def __hash__(self):
            return hash(self.value)

        def __eq__(self, other: Any) -> bool:
            if not isinstance(other, ParseResult.CharValue):
                return NotImplemented
            elif self is other:
                return True
            else:
                return other.vtype == self.vtype and other.value == self.value and other.name == self.name

        def __str__(self):
            return "<CharValue {!r:s} name={}>".format(self.value, self.name)

    class RegisterValue(Value):
        def __init__(self, register: str, name: str=None) -> None:
            super().__init__(VariableType.REGISTER, name)
            self.register = register.lower()

        def __hash__(self):
            return hash((self.vtype, self.register, self.name))

        def __eq__(self, other: Any) -> bool:
            if not isinstance(other, ParseResult.RegisterValue):
                return NotImplemented
            elif self is other:
                return True
            else:
                return other.vtype == self.vtype and other.register == self.register and other.name == self.name

        def __str__(self):
            return "<RegisterValue {:s} name={}>".format(self.register, self.name)

        def assignable_from(self, other: 'ParseResult.Value') -> bool:
            if isinstance(other, ParseResult.RegisterValue) and len(self.register) != len(other.register):
                return False
            if isinstance(other, ParseResult.StringValue) and len(self.register) < 2:
                return False
            if isinstance(other, ParseResult.ConstantValue):
                return other.value < 0x100 or len(self.register) > 1
            if isinstance(other, ParseResult.PlaceholderSymbol):
                return True
            return other.vtype in {VariableType.BYTE, VariableType.REGISTER, VariableType.CHARACTER} or other.vtype in STRING_VARTYPES

    class MemMappedValue(Value):
        def __init__(self, address: int, vartype: VariableType, length: int, name: str=None) -> None:
            super().__init__(vartype, name)
            self.address = address
            self.length = length

        def __hash__(self):
            return hash((self.vtype, self.address, self.length, self.name))

        def __eq__(self, other: Any) -> bool:
            if not isinstance(other, ParseResult.MemMappedValue):
                return NotImplemented
            elif self is other:
                return True
            else:
                return other.vtype == self.vtype and other.address == self.address and \
                       other.length == self.length and other.name == self.name

        def __str__(self):
            if self.address < 0x100:
                return "<MemMappedValue ${:02x} #={:d} name={}>".format(self.address, self.length, self.name)
            else:
                return "<MemMappedValue ${:04x} #={:d} name={}>".format(self.address, self.length, self.name)

        def assignable_from(self, other: 'ParseResult.Value') -> bool:
            if isinstance(other, ParseResult.PlaceholderSymbol):
                return True
            elif self.vtype == VariableType.BYTE:
                return other.vtype in {VariableType.BYTE, VariableType.CONSTANT, VariableType.REGISTER, VariableType.CHARACTER}
            elif self.vtype == VariableType.WORD:
                return other.vtype in {VariableType.WORD, VariableType.BYTE,
                                       VariableType.CONSTANT, VariableType.REGISTER, VariableType.CHARACTER}
            return False

    class _Stmt:
        def resolve_pass_2(self, parser: 'Parser', cur_block: 'ParseResult.Block',
                           stmt_index: int, statements: List['ParseResult._Stmt']) -> None:
            pass

    class Label(_Stmt):
        def __init__(self, name: str, linenum: int) -> None:
            self.name = name
            self.linenum = linenum

    class AssignmentStmt(_Stmt):
        def __init__(self, leftvalues: List['ParseResult.Value'], right: 'ParseResult.Value', linenum: int) -> None:
            self.leftvalues = leftvalues
            self.right = right
            self.linenum = linenum

        def __str__(self):
            return "<Assign {:s} to {:s}>".format(str(self.right), ",".join(str(lv) for lv in self.leftvalues))

        def resolve_pass_2(self, parser: 'Parser', cur_block: 'ParseResult.Block',
                           stmt_index: int, statements: List['ParseResult._Stmt']) -> None:
            if isinstance(self.right, ParseResult.PlaceholderSymbol):
                value = parser.parse_value(self.right.name, cur_block)
                if isinstance(value, ParseResult.PlaceholderSymbol):
                    raise ParseError(cur_block.sourcefile, cur_block.linenum, "", "cannot resolve symbol: " + self.right.name)
                self.right = value
            lv_resolved = []
            for lv in self.leftvalues:
                if isinstance(lv, ParseResult.PlaceholderSymbol):
                    value = parser.parse_value(lv.name, cur_block)
                    if isinstance(value, ParseResult.PlaceholderSymbol):
                        raise ParseError(cur_block.sourcefile, cur_block.linenum, "", "cannot resolve symbol: " + lv.name)
                    lv_resolved.append(value)
                else:
                    lv_resolved.append(lv)
            self.leftvalues = lv_resolved
            if any(isinstance(lv, ParseResult.PlaceholderSymbol) for lv in self.leftvalues) or \
               isinstance(self.right, ParseResult.PlaceholderSymbol):
                raise ParseError(cur_block.sourcefile, cur_block.linenum, "",
                                 "unresolved placeholders in assignment statement")
            # check assignability again
            for lv in self.leftvalues:
                if not lv.assignable_from(self.right):
                    raise ParseError(cur_block.sourcefile, cur_block.linenum, "", "cannot assign {0} to {1}".format(self.right, lv))

    class ReturnStmt(_Stmt):
        def __init__(self, a: Optional['ParseResult.Value']=None,
                     x: Optional['ParseResult.Value']=None,
                     y: Optional['ParseResult.Value']=None) -> None:
            self.a = a
            self.x = x
            self.y = y

        def resolve_pass_2(self, parser: 'Parser', cur_block: 'ParseResult.Block',
                           stmt_index: int, statements: List['ParseResult._Stmt']) -> None:
            if isinstance(self.a, ParseResult.PlaceholderSymbol) or \
               isinstance(self.x, ParseResult.PlaceholderSymbol) or \
               isinstance(self.y, ParseResult.PlaceholderSymbol):
                raise ParseError(cur_block.sourcefile, cur_block.linenum, "",
                                 "unresolved placeholders in returnstatement")

    class IncrDecrStmt(_Stmt):
        def __init__(self, what: 'ParseResult.Value', howmuch: int) -> None:
            self.what = what
            self.howmuch = howmuch

        def resolve_pass_2(self, parser: 'Parser', cur_block: 'ParseResult.Block',
                           stmt_index: int, statements: List['ParseResult._Stmt']) -> None:
            if isinstance(self.what, ParseResult.PlaceholderSymbol):
                value = parser.parse_value(self.what.name, cur_block)
                if isinstance(value, ParseResult.PlaceholderSymbol):
                    raise ParseError(cur_block.sourcefile, cur_block.linenum, "", "cannot resolve symbol: " + self.what.name)
                self.what = value

    class CallStmt(_Stmt):
        def __init__(self, label: str=None, address: Optional[int]=None, unresolved: str=None, is_goto: bool=False) -> None:
            if label and address:
                raise ValueError("can only set either a label or an absolute address")
            self.label = label
            self.address = address
            self.subroutine = None      # type: SubroutineIdentifier
            self.unresolved = unresolved
            self.is_goto = is_goto

        def resolve_pass_2(self, parser: 'Parser', cur_block: 'ParseResult.Block',
                           stmt_index: int, statements: List['ParseResult._Stmt']) -> None:
            if self.unresolved:
                identifier, local = parser.result.lookup_symbol(self.unresolved, cur_block)
                if not identifier:
                    raise ParseError(cur_block.sourcefile, cur_block.linenum, "",
                                     "unknown symbol '{:s}' used in this block".format(self.unresolved))
                if isinstance(identifier, SubroutineIdentifier):
                    self.subroutine = identifier
                if local:
                    self.label = identifier.name
                else:
                    self.label = "{:s}.{:s}".format(identifier.block, identifier.name)
                self.unresolved = None

    class InlineAsm(_Stmt):
        def __init__(self, linenum: int, asmlines: List[str]) -> None:
            self.linenum = linenum
            self.asmlines = asmlines

    def __init__(self, sourcefile: str) -> None:
        self.format = ProgramFormat.RAW
        self.with_sys = False
        self.sourcefile = sourcefile
        self.clobberzp = False
        self.restorezp = False
        self.blocks = []          # type: List['ParseResult.Block']

    def add_block(self, block: 'ParseResult.Block', position: Optional[int]=None) -> None:
        if position is not None:
            self.blocks.insert(position, block)
        else:
            self.blocks.append(block)

    def merge(self, parsed: 'ParseResult') -> None:
        self.blocks.extend(parsed.blocks)

    def lookup_symbol(self, name: str, localblock: Block) -> Tuple[Optional[Identifier], bool]:
        name1, sep, name2 = name.partition(".")
        if sep:
            for b in self.blocks:
                if b.name == name1:
                    if name2 in b.symbols:
                        return b.symbols[name2], name1 == localblock.name
                    return None, False
        elif name1 in localblock.symbols:
            return localblock.symbols[name1], True
        return None, False


class Parser:
    def __init__(self, sourcefile: str, sourcecode: Optional[str]=None, zeropage: Zeropage=None) -> None:
        self.result = ParseResult(sourcefile)
        self.zeropage = zeropage
        self.sourcefile = sourcefile
        self.cur_linenum = -1
        self.cur_lineidx = -1
        self.cur_block = None  # type: ParseResult.Block
        if sourcecode:
            sourcelines = sourcecode.splitlines()
        else:
            with open(self.sourcefile, "rU") as source:
                sourcelines = source.readlines()
        # store all lines that are not empty or a comment, and strip any other comments
        self.lines = []  # type: List[Tuple[int, str]]
        for num, line in enumerate(sourcelines, start=1):
            line2 = line.strip()
            if not line2 or line2.startswith(";"):
                continue
            self.lines.append((num, line.partition(";")[0].rstrip()))  # get rid of any comments at the end of the line

    def parse(self) -> Optional[ParseResult]:
        # start the parsing
        try:
            return self._parse()
        except ParseError as x:
            print("Error:", str(x))
            if x.sourceline:
                print("\tsource text: '{:s}'".format(x.sourceline))
            raise   # XXX
            return None

    def _parse(self) -> ParseResult:
        print("parsing (pass 1)", self.sourcefile)
        self.parse_header()
        if not self.zeropage:
            self.zeropage = Zeropage(self.result.clobberzp)
        while True:
            next_line = self.peek_next_line()[1]
            if next_line.lstrip().startswith("~"):
                self.result.add_block(self.parse_block())
            elif next_line.lstrip().startswith(".include"):
                parsed_include = self.parse_include()
                if parsed_include:
                    self.result.merge(parsed_include)
                else:
                    raise self.PError("Error while parsing included file")
            else:
                break
        _, line = self.next_line()
        if line:
            raise self.PError("missing block or invalid characters")
        # check if we have a proper main block to contain the program's entry point (if making a prg)
        if self.result.format == ProgramFormat.PRG:
            for block in self.result.blocks:
                if block.name == "main":
                    if "start" not in block.label_names:
                        self.cur_linenum = block.linenum
                        raise self.PError("The 'main' block should contain the program entry point 'start'")
                    if not any(s for s in block.statements if isinstance(s, ParseResult.ReturnStmt)):
                        print("Warning: {:s}:{:d}: The 'main' block is lacking a return statement.".format(self.sourcefile, block.linenum))
                    break
            else:
                raise self.PError("A block named 'main' should be defined for the program's entry point 'start'")
        # parsing pass 2
        print("parsing (pass 2)", self.sourcefile)
        # fix up labels that are unknown:
        for block in self.result.blocks:
            statements = list(block.statements)
            for index, stmt in enumerate(statements):
                try:
                    stmt.resolve_pass_2(self, block, index, statements)
                except LookupError as x:
                    self.cur_linenum = block.linenum
                    raise self.PError("Symbol reference error in this block") from x
            block.statements = statements
        # done parsing.
        return self.result

    def next_line(self) -> Tuple[int, str]:
        self.cur_lineidx += 1
        try:
            self.cur_linenum, line = self.lines[self.cur_lineidx]
            return self.cur_linenum, line
        except IndexError:
            return -1, ""

    def prev_line(self) -> Tuple[int, str]:
        self.cur_lineidx -= 1
        self.cur_linenum, line = self.lines[self.cur_lineidx]
        return self.cur_linenum, line

    def peek_next_line(self) -> Tuple[int, str]:
        if (self.cur_lineidx + 1) < len(self.lines):
            return self.lines[self.cur_lineidx + 1]
        return -1, ""

    def PError(self, message: str) -> ParseError:
        try:
            sourceline = self.lines[self.cur_lineidx][1].strip()
        except IndexError:
            sourceline = ""
        return ParseError(self.sourcefile, self.cur_linenum, sourceline, message)

    def parse_header(self) -> None:
        self.result.with_sys = False
        self.result.format = ProgramFormat.RAW
        while True:
            num, line = self.next_line()
            if line.startswith("output"):
                _, _, arg = line.partition(" ")
                arg = arg.lstrip()
                self.result.with_sys = False
                self.result.format = ProgramFormat.RAW
                if arg == "raw":
                    pass
                elif arg == "prg":
                    self.result.format = ProgramFormat.PRG
                elif arg == "prg,sys":
                    self.result.with_sys = True
                    self.result.format = ProgramFormat.PRG
                else:
                    raise self.PError("invalid output format")
            elif line.startswith("clobberzp"):
                self.result.clobberzp = True
                _, _, arg = line.partition(" ")
                arg = arg.lstrip()
                if arg == "restore":
                    self.result.restorezp = True
                elif arg == "":
                    pass
                else:
                    raise self.PError("invalid arg for clobberzp")
            else:
                self.prev_line()
                return

    def parse_include(self) -> ParseResult:
        num, line = self.next_line()
        line = line.lstrip()
        if not line.startswith(".include"):
            raise self.PError("expected .include")
        _, arg = line.split(maxsplit=1)
        if not arg.startswith('"') or not arg.endswith('"'):
            raise self.PError("filename must be between quotes")
        filename = arg[1:-1].strip()
        if os.path.isfile(filename):
            parser = Parser(filename, zeropage=self.zeropage)
            return parser.parse()
        else:
            # try to find the included file in the same location as the sourcefile being compiled
            filename = os.path.join(os.path.split(self.sourcefile)[0], filename)
            if os.path.isfile(filename):
                parser = Parser(filename, zeropage=self.zeropage)
                return parser.parse()
        raise FileNotFoundError("Included file not found: " + filename)

    def parse_block(self) -> ParseResult.Block:
        # first line contains block header "~ [name] [addr]" followed by a '{'
        num, line = self.next_line()
        line = line.lstrip()
        if not line.startswith("~"):
            raise self.PError("expected '~' (block)")
        self.cur_block = ParseResult.Block(self.sourcefile, num, self.zeropage)
        block_args = line[1:].split()
        self.cur_block.name = "il65_block_{:d}".format(len(self.result.blocks))
        arg = ""
        while block_args:
            arg = block_args.pop(0)
            if arg.isidentifier():
                if arg in set(b.name for b in self.result.blocks):
                    raise self.PError("duplicate block name")
                self.cur_block.name = arg
            elif arg == "{":
                break
            else:
                try:
                    self.cur_block.address = self.parse_number(arg)
                except ParseError:
                    raise self.PError("Invalid number or block name")
                if self.cur_block.address == 0:
                    raise self.PError("block address must be > 0 (or omitted)")
        if arg != "{":
            _, line = self.peek_next_line()
            if line != "{":
                raise self.PError("expected '{' after block")
            else:
                self.next_line()
        while True:
            _, line = self.next_line()
            unstripped_line = line
            line = line.strip()
            if line == "}":
                return self.cur_block
            if line.startswith("asm"):
                self.prev_line()
                self.cur_block.statements.append(self.parse_asm())
                continue
            elif line.startswith("var"):
                self.parse_dot_var(line)
            elif line.startswith("const"):
                self.parse_dot_const(line)
            elif line.startswith("memory"):
                self.parse_dot_memory(line)
            elif line.startswith("subx"):
                self.parse_dot_subx(line)
            elif unstripped_line.startswith((" ", "\t")):
                self.cur_block.statements.append(self.parse_statement(line))
                continue
            elif line:
                self.parse_label(line)
            else:
                raise self.PError("missing } to close block from line " + str(self.cur_block.linenum))

    def parse_label(self, line: str) -> None:
        label_line = line.split(maxsplit=1)
        if str.isidentifier(label_line[0]):
            labelname = label_line[0]
            if labelname in self.cur_block.label_names:
                raise self.PError("label already defined")
            if labelname in self.cur_block.symbols:
                raise self.PError("symbol already defined")
            self.cur_block.symbols.define_label(self.cur_block.name, labelname, self.sourcefile, self.cur_linenum)
            self.cur_block.statements.append(ParseResult.Label(labelname, self.cur_linenum))
            if len(label_line) > 1:
                rest = label_line[1]
                self.cur_block.statements.append(self.parse_statement(rest))
        else:
            raise self.PError("invalid label name")

    def parse_dot_memory(self, line: str) -> None:
        dotargs = line.split()
        if dotargs[0] != "memory" or len(dotargs) not in (3, 4):
            raise self.PError("invalid memory definition")
        msize = 1
        mtype = VariableType.BYTE
        memtype = dotargs[1]
        matrixsize = None
        if memtype.startswith("."):
            if memtype == ".byte":
                pass
            elif memtype == ".word":
                msize = 2
                mtype = VariableType.WORD
            elif memtype.startswith(".array(") and memtype.endswith(")"):
                msize = self._size_from_arraydecl(memtype)
                mtype = VariableType.BYTEARRAY
            elif memtype.startswith(".wordarray(") and memtype.endswith(")"):
                msize = self._size_from_arraydecl(memtype)
                mtype = VariableType.WORDARRAY
            elif memtype.startswith(".matrix(") and memtype.endswith(")"):
                if len(dotargs) != 4:
                    raise self.PError("missing matrix memory address")
                matrixsize = self._size_from_matrixdecl(memtype)
                msize = matrixsize[0] * matrixsize[1]
                mtype = VariableType.MATRIX
            else:
                raise self.PError("invalid memory type")
            dotargs.pop(1)
        if len(dotargs) < 3:
            raise self.PError("invalid memory definition")
        varname = dotargs[1]
        if not varname.isidentifier():
            raise self.PError("invalid symbol name")
        memaddress = self.parse_number(dotargs[2])
        try:
            self.cur_block.symbols.define_variable(self.cur_block.name, varname, self.sourcefile, self.cur_linenum, mtype,
                                                   length=msize, address=memaddress, matrixsize=matrixsize)
        except SymbolError as x:
            raise self.PError(str(x)) from x

    def parse_dot_const(self, line: str) -> None:
        dotargs = line.split()
        if dotargs[0] != "const" or len(dotargs) != 3:
            raise self.PError("invalid const definition")
        varname = dotargs[1]
        if not varname.isidentifier():
            raise self.PError("invalid symbol name")
        if dotargs[2] in REGISTER_SYMBOLS:
            try:
                self.cur_block.symbols.define_variable(self.cur_block.name, varname, self.sourcefile, self.cur_linenum,
                                                       VariableType.REGISTER, register=dotargs[2])
            except SymbolError as x:
                raise self.PError(str(x)) from x
        else:
            constvalue = self.parse_number(dotargs[2])
            try:
                self.cur_block.symbols.define_variable(self.cur_block.name, varname, self.sourcefile, self.cur_linenum,
                                                       VariableType.CONSTANT, value=constvalue)
            except SymbolError as x:
                raise self.PError(str(x)) from x

    def parse_dot_subx(self, line: str) -> None:
        #  subx P_CHROUT (char: A) -> (A,X,Y)     $ffd2
        #  subx SUBNAME (PARAMETERS) -> (RESULTS)  ADDRESS
        match = re.match(r"^subx\s+(?P<name>\w+)\s+"
                         r"\((?P<parameters>[\w\s:,]*)\)"
                         r"\s*->\s*"
                         r"\((?P<results>[\w\s?,]*)\)\s*"
                         r"(?P<address>\S*)\s*$", line)
        if not match:
            raise self.PError("invalid subx declaration")
        name, parameterlist, resultlist, address_str = \
            match.group("name"), match.group("parameters"), match.group("results"), match.group("address")
        parameters = [(match.group("name"), match.group("target"))
                      for match in re.finditer(r"(?:(?P<name>[\w]+)\s*:\s*(?P<target>[\w]+))(?:,|$)", parameterlist)]
        results = {match.group("name") for match in re.finditer(r"\s*(?P<name>\w\?+)\s*(?:,|$)", resultlist)}
        address = self.parse_number(address_str)
        self.cur_block.symbols.define_sub(self.cur_block.name, name, self.sourcefile, self.cur_linenum, parameters, results, address)

    def parse_dot_var(self, line: str) -> None:
        match = re.match(r"^var\s+.(?P<type>(?:s|p|ps|)text)\s+(?P<name>\w+)\s+(?P<value>['\"].+['\"])$", line)
        if match:
            # it's a var string definition.
            vtype = {
                "text": VariableType.STRING,
                "ptext": VariableType.STRING_P,
                "stext": VariableType.STRING_S,
                "pstext": VariableType.STRING_PS
            }[match.group("type")]
            vname = match.group("name")
            strvalue = self.parse_string(match.group("value"))
            try:
                self.cur_block.symbols.define_variable(self.cur_block.name, vname,
                                                       self.sourcefile, self.cur_linenum, vtype, value=strvalue)
            except SymbolError as x:
                raise self.PError(str(x)) from x
            return

        args = line.split()
        if args[0] != "var" or len(args) < 2 or len(args) > 5:
            print("ARGS", args, len(args))  # XXX
            raise self.PError("invalid var decl (1)")

        def get_vtype(vtype: str) -> Tuple[VariableType, Union[int, Tuple[int, int]]]:
            if vtype == ".byte":
                return VariableType.BYTE, 1
            elif vtype == ".word":
                return VariableType.WORD, 1
            elif vtype.startswith(".array(") and vtype.endswith(")"):
                return VariableType.BYTEARRAY, self._size_from_arraydecl(vtype)
            elif vtype.startswith(".wordarray(") and vtype.endswith(")"):
                return VariableType.WORDARRAY, self._size_from_arraydecl(vtype)
            elif vtype.startswith(".matrix(") and vtype.endswith(")"):
                return VariableType.MATRIX, self._size_from_matrixdecl(vtype)
            else:
                raise self.PError("invalid variable type")

        vaddr = None
        value = 0
        matrixsize = None  # type: Tuple[int, int]
        if len(args) == 2:  # var uninit_bytevar
            vname = args[1]
            if not vname.isidentifier():
                raise self.PError("invalid variable name")
            vtype = VariableType.BYTE
            vlen = 1
        elif len(args) == 3:  # var vartype varname
            vname = args[2]
            if not vname.isidentifier():
                raise self.PError("invalid variable name, or maybe forgot variable type")
            vtype, vlen = get_vtype(args[1])   # type: ignore
        elif len(args) == 4:  # var vartype varname value
            vname = args[2]
            if not vname.isidentifier():
                raise self.PError("invalid variable name")
            vtype, vlen = get_vtype(args[1])   # type: ignore
            value = self.parse_number(args[3])
        else:
            raise self.PError("invalid var decl (2)")
        if vtype == VariableType.MATRIX:
            matrixsize = vlen   # type: ignore
            vlen = None
        try:
            self.cur_block.symbols.define_variable(self.cur_block.name, vname, self.sourcefile, self.cur_linenum, vtype,
                                                   address=vaddr, length=vlen, value=value, matrixsize=matrixsize)
        except SymbolError as x:
            raise self.PError(str(x)) from x

    def parse_statement(self, line: str) -> ParseResult._Stmt:
        lhs, sep, rhs = line.partition("=")
        if sep:
            return self.parse_assignment(line)
        elif line.startswith("return"):
            return self.parse_return(line)
        elif line.endswith(("++", "--")):
            incr = line.endswith("++")
            what = self.parse_value(line[:-2].rstrip())
            if isinstance(what, ParseResult.ConstantValue):
                raise self.PError("cannot in/decrement a constant value")
            return ParseResult.IncrDecrStmt(what, 1 if incr else -1)
        elif line.startswith("call"):
            return self.parse_call_or_go(line, "call")
        elif line.startswith("go"):
            return self.parse_call_or_go(line, "go")
        else:
            raise self.PError("invalid statement")

    def parse_call_or_go(self, line: str, what: str) -> ParseResult.CallStmt:
        args = line.split()
        if len(args) != 2:
            raise self.PError("invalid call/go arguments")
        if what == "go":
            return ParseResult.CallStmt(unresolved=args[1], is_goto=True)
        elif what == "call":
            return ParseResult.CallStmt(unresolved=args[1], is_goto=False)
        else:
            raise ValueError("invalid what")

    def parse_assignment(self, line: str) -> ParseResult.AssignmentStmt:
        # parses assigning a value to one or more targets
        parts = line.split("=")
        rhs = parts.pop()
        l_values = [self.parse_value(part) for part in parts]
        if any(isinstance(lv, ParseResult.ConstantValue) for lv in l_values):
            raise self.PError("can't have a constant as assignment target, did you mean [name] instead?")
        r_value = self.parse_value(rhs)
        for lv in l_values:
            if not lv.assignable_from(r_value):
                raise self.PError("cannot assign {0} to {1}".format(r_value, lv))
        return ParseResult.AssignmentStmt(l_values, r_value, self.cur_linenum)

    def parse_return(self, line: str) -> ParseResult.ReturnStmt:
        parts = line.split(maxsplit=1)
        if parts[0] != "return":
            raise self.PError("invalid statement, return expected")
        a = x = y = None
        values = []  # type: List[str]
        if len(parts) > 1:
            values = parts[1].split(",")
        if len(values) == 0:
            return ParseResult.ReturnStmt()
        else:
            a = self.parse_value(values[0]) if values[0] else None
            if len(values) > 1:
                x = self.parse_value(values[1]) if values[1] else None
                if len(values) > 2:
                    y = self.parse_value(values[2]) if values[2] else None
                    if len(values) > 3:
                        raise self.PError("too many returnvalues")
        return ParseResult.ReturnStmt(a, x, y)

    def parse_asm(self) -> ParseResult.InlineAsm:
        asm_line_num, line = self.next_line()
        aline = line.split()
        if not len(aline) == 2 or aline[0] != "asm" or aline[1] != "{":
            raise self.PError("invalid asm start")
        asmlines = []   # type: List[str]
        while True:
            num, line = self.next_line()
            if line.strip() == "}":
                return ParseResult.InlineAsm(asm_line_num, asmlines)
            asmlines.append(line)

    def parse_value(self, value: str, cur_block: Optional[ParseResult.Block]=None) -> ParseResult.Value:
        cur_block = cur_block or self.cur_block
        value = value.strip()
        if not value:
            raise self.PError("value expected")
        if value[0] in "0123456789$%":
            return ParseResult.ConstantValue(self.parse_number(value))
        elif value in REGISTER_SYMBOLS:
            return ParseResult.RegisterValue(value)
        elif (value.startswith("'") and value.endswith("'")) or (value.startswith('"') and value.endswith('"')):
            strvalue = self.parse_string(value)
            if len(strvalue) == 1:
                return ParseResult.CharValue(strvalue)
            return ParseResult.StringValue(strvalue)
        elif value == "true":
            return ParseResult.ConstantValue(1)
        elif value == "false":
            return ParseResult.ConstantValue(0)
        elif self.is_identifier(value):
            sym, local = self.result.lookup_symbol(value, cur_block)
            if sym is None:
                # symbols is not (yet) known, store a placeholder to resolve later in parse pass 2
                return ParseResult.PlaceholderSymbol(None, value)
            elif isinstance(sym, VariableIdentifier):
                if local:
                    symbolname = sym.name
                else:
                    symbolname = "{:s}.{:s}".format(sym.block, sym.name)
                if sym.type == VariableType.REGISTER:
                    return ParseResult.RegisterValue(sym.register, name=symbolname)
                elif sym.type == VariableType.CONSTANT:
                    return ParseResult.ConstantValue(sym.value, name=symbolname)   # type: ignore
                elif sym.type == VariableType.CHARACTER:
                    return ParseResult.CharValue(sym.value, name=symbolname)       # type: ignore
                elif sym.type in (VariableType.BYTE, VariableType.WORD):
                    return ParseResult.MemMappedValue(sym.address, sym.type, sym.length, name=symbolname)
                elif sym.type in STRING_VARTYPES:
                    return ParseResult.StringValue(sym.value, name=symbolname)     # type: ignore
                else:
                    raise self.PError("invalid symbol type (1)")
            else:
                raise self.PError("invalid symbol type (2)")
        elif value.startswith('[') and value.endswith(']'):
            num_or_name = value[1:-1].strip()
            if num_or_name.isidentifier():
                try:
                    sym = cur_block.symbols[num_or_name]    # type: ignore
                except KeyError:
                    raise self.PError("unknown symbol (2): " + num_or_name)
                if isinstance(sym, VariableIdentifier):
                    if sym.type == VariableType.CONSTANT:
                        # XXX word type how? .w in stmt?
                        return ParseResult.MemMappedValue(sym.value, VariableType.BYTE, length=1, name=sym.name)    # type: ignore
                    else:
                        raise self.PError("invalid symbol type used as lvalue of assignment (3)")
                else:
                    raise self.PError("invalid symbol type used as lvalue of assignment (4)")
            else:
                addr = self.parse_number(num_or_name)
                return ParseResult.MemMappedValue(addr, VariableType.BYTE, length=1)   # XXX word type how? .w in statement?
        else:
            raise self.PError("invalid value '"+value+"'")

    def is_identifier(self, name: str) -> bool:
        if name.isidentifier():
            return True
        blockname, sep, name = name.partition(".")
        if sep:
            return blockname.isidentifier() and name.isidentifier()
        return False

    def parse_number(self, number: str) -> int:
        try:
            if number[0] in "0123456789":
                a = int(number)
            elif number.startswith("$"):
                a = int(number[1:], 16)
            elif number.startswith("%"):
                a = int(number[1:], 2)
            else:
                raise self.PError("invalid number; " + number)
            if 0 <= a <= 0xffff:
                return a
            raise ValueError("out of bounds")
        except ValueError as vx:
            raise self.PError("invalid number; "+str(vx))

    def parse_string(self, string: str) -> str:
        if string.startswith("'") and not string.endswith("'") or string.startswith('"') and not string.endswith('"'):
            raise self.PError("mismatched string quotes")
        return ast.literal_eval(string)

    def _size_from_arraydecl(self, decl: str) -> int:
        return self.parse_number(decl[:-1].split("(")[-1])

    def _size_from_matrixdecl(self, decl: str) -> Tuple[int, int]:
        decl = decl[:-1].split("(")[-1]
        xs, ys = decl.split(",")
        return self.parse_number(xs), self.parse_number(ys)


class Optimizer:
    def __init__(self, parseresult: ParseResult) -> None:
        self.parsed = parseresult

    def optimize(self) -> ParseResult:
        print("optimizing", self.parsed.sourcefile)
        for block in self.parsed.blocks:
            self.combine_assignments_into_multi(block)
            self.optimize_multiassigns(block)
            self.discard_assignments_without_effect(block)
        return self.parsed

    def discard_assignments_without_effect(self, block: ParseResult.Block) -> None:
        # consecutive assignment statements with same lvalue should be removed and only keep the last one
        statements = list(block.statements)
        previous_assignment_idx = -1
        for i, stmt in enumerate(statements):
            if isinstance(stmt, ParseResult.AssignmentStmt):
                if previous_assignment_idx >= 0:
                    pa = statements[previous_assignment_idx]
                    if isinstance(pa, ParseResult.AssignmentStmt):
                        if pa.leftvalues == stmt.leftvalues:
                            print("{:s}:{:d} assignment without effect removed".format(block.sourcefile, pa.linenum))
                            statements[previous_assignment_idx] = None
                previous_assignment_idx = i
            else:
                previous_assignment_idx = -1
        block.statements = [s for s in statements if s]

    def optimize_multiassigns(self, block: ParseResult.Block) -> None:
        # optimize multi-assign statements.
        for stmt in block.statements:
            if isinstance(stmt, ParseResult.AssignmentStmt) and len(stmt.leftvalues) > 1:
                # remove duplicates
                lvalues = list(set(stmt.leftvalues))
                if len(lvalues) != len(stmt.leftvalues):
                    print("{:s}:{:d} removed duplicate assignment targets".format(block.sourcefile, stmt.linenum))
                # change order: first registers, then zp addresses, then non-zp addresses, then the rest (if any)
                stmt.leftvalues = list(sorted(lvalues, key=value_sortkey))

    def combine_assignments_into_multi(self, block: ParseResult.Block) -> None:
        # fold multiple consecutive assignments with the same rvalue into one multi-assignment
        statements = []   # type: List[ParseResult._Stmt]
        multi_assign_statement = None
        for stmt in block.statements:
            if isinstance(stmt, ParseResult.AssignmentStmt):
                if multi_assign_statement and multi_assign_statement.right == stmt.right:
                    multi_assign_statement.leftvalues.extend(stmt.leftvalues)
                    print("{:s}:{:d} joined with previous line into multi-assign statement".format(block.sourcefile, stmt.linenum))
                else:
                    if multi_assign_statement:
                        statements.append(multi_assign_statement)
                    multi_assign_statement = stmt
            else:
                if multi_assign_statement:
                    statements.append(multi_assign_statement)
                    multi_assign_statement = None
                statements.append(stmt)
        if multi_assign_statement:
            statements.append(multi_assign_statement)
        block.statements = statements


def value_sortkey(value: ParseResult.Value) -> int:
    if isinstance(value, ParseResult.RegisterValue):
        num = 0
        for char in value.register:
            num *= 100
            num += ord(char)
        return num
    elif isinstance(value, ParseResult.MemMappedValue):
        if value.address < 0x100:
            return 10000 + value.address
        else:
            return 20000 + value.address
    else:
        return 99999999
