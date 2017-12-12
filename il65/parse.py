"""
Intermediate Language for 6502/6510 microprocessors

Written by Irmen de Jong (irmen@razorvine.net)
License: GNU GPL 3.0, see LICENSE
"""

import sys
import re
import os
import ast
import shutil
import enum
from typing import Set, List, Tuple, Optional, Union, Any, Dict
from symbols import SymbolTable, Zeropage, DataType, SymbolDefinition, SubroutineDef, \
    check_value_in_range, trunc_float_if_needed, \
    VariableDef, ConstantDef, SymbolError, STRING_DATATYPES, REGISTER_SYMBOLS, REGISTER_WORDS, REGISTER_BYTES


# 5-byte cbm MFLPT format limitations:
FLOAT_MAX_POSITIVE = 1.7014118345e+38
FLOAT_MAX_NEGATIVE = -1.7014118345e+38

RESERVED_NAMES = {"true", "false", "var", "memory", "const", "asm"}
RESERVED_NAMES |= REGISTER_SYMBOLS


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
        _unnamed_block_labels = {}  # type: Dict[ParseResult.Block, str]

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

        @property
        def label(self) -> str:
            if self.name:
                return self.name
            if self in self._unnamed_block_labels:
                return self._unnamed_block_labels[self]
            label = "il65_block_{:d}".format(len(self._unnamed_block_labels))
            self._unnamed_block_labels[self] = label
            return label

    class Value:
        def __init__(self, datatype: DataType, name: str=None, constant: bool=False) -> None:
            self.datatype = datatype
            self.name = name
            self.constant = constant

        def assignable_from(self, other: 'ParseResult.Value') -> Tuple[bool, str]:
            if self.constant:
                return False, "cannot assign to a constant"
            return False, "incompatible value for assignment"

    class PlaceholderSymbol(Value):
        def assignable_from(self, other: 'ParseResult.Value') -> Tuple[bool, str]:
            return True, ""

        def __str__(self):
            return "<Placeholder unresolved {:s}>".format(self.name)

    class IntegerValue(Value):
        def __init__(self, value: Optional[int], *, datatype: DataType=None, name: str=None) -> None:
            if type(value) is int:
                if datatype is None:
                    if 0 <= value < 0x100:
                        datatype = DataType.BYTE
                    elif value < 0x10000:
                        datatype = DataType.WORD
                    else:
                        raise OverflowError("value too big: ${:x}".format(value))
                else:
                    faultreason = check_value_in_range(datatype, "", 1, value)
                    if faultreason:
                        raise OverflowError(faultreason)
                super().__init__(datatype, name, True)
            else:
                raise TypeError("invalid data type")
            self.value = value

        def __hash__(self):
            return hash((self.datatype, self.value, self.name))

        def __eq__(self, other: Any) -> bool:
            if not isinstance(other, ParseResult.IntegerValue):
                return NotImplemented
            elif self is other:
                return True
            else:
                return other.datatype == self.datatype and other.value == self.value and other.name == self.name

        def __str__(self):
            return "<IntegerValue {} name={}>".format(self.value, self.name)

    class FloatValue(Value):
        def __init__(self, value: float, name: str=None) -> None:
            if type(value) is float:
                super().__init__(DataType.FLOAT, name, True)
                self.value = value
            else:
                raise TypeError("invalid data type")

        def __hash__(self):
            return hash((self.datatype, self.value, self.name))

        def __eq__(self, other: Any) -> bool:
            if not isinstance(other, ParseResult.FloatValue):
                return NotImplemented
            elif self is other:
                return True
            else:
                return other.datatype == self.datatype and other.value == self.value and other.name == self.name

        def __str__(self):
            return "<FloatValue {} name={}>".format(self.value, self.name)

    class StringValue(Value):
        def __init__(self, value: str, name: str=None, constant: bool=False) -> None:
            super().__init__(DataType.STRING, name, constant)
            self.value = value

        def __hash__(self):
            return hash((self.datatype, self.value, self.name))

        def __eq__(self, other: Any) -> bool:
            if not isinstance(other, ParseResult.StringValue):
                return NotImplemented
            elif self is other:
                return True
            else:
                return other.datatype == self.datatype and other.value == self.value and other.name == self.name

        def __str__(self):
            return "<StringValue {!r:s} name={} constant={}>".format(self.value, self.name, self.constant)

    class RegisterValue(Value):
        def __init__(self, register: str, datatype: DataType, name: str=None) -> None:
            assert datatype in (DataType.BYTE, DataType.WORD)
            assert register in REGISTER_SYMBOLS
            super().__init__(datatype, name, False)
            self.register = register

        def __hash__(self):
            return hash((self.datatype, self.register, self.name))

        def __eq__(self, other: Any) -> bool:
            if not isinstance(other, ParseResult.RegisterValue):
                return NotImplemented
            elif self is other:
                return True
            else:
                return other.datatype == self.datatype and other.register == self.register and other.name == self.name

        def __str__(self):
            return "<RegisterValue {:s} type {:s} name={}>".format(self.register, self.datatype, self.name)

        def assignable_from(self, other: 'ParseResult.Value') -> Tuple[bool, str]:
            if self.constant:
                return False, "cannot assign to a constant"
            if isinstance(other, ParseResult.RegisterValue) and len(self.register) != len(other.register):
                return False, "register size mismatch"
            if isinstance(other, ParseResult.StringValue) and self.register in REGISTER_BYTES:
                return False, "string address requires 16 bits combined register"
            if isinstance(other, (ParseResult.IntegerValue, ParseResult.FloatValue)):
                range_error = check_value_in_range(self.datatype, self.register, 1, other.value)
                if range_error:
                    return False, range_error
                return True, ""
            if isinstance(other, ParseResult.PlaceholderSymbol):
                return True, ""
            if self.datatype == DataType.BYTE:
                if other.datatype != DataType.BYTE:
                    return False, "(unsigned) byte required"
                return True, ""
            if self.datatype == DataType.WORD:
                if other.datatype in (DataType.BYTE, DataType.WORD) or other.datatype in STRING_DATATYPES:
                    return True, ""
                return False, "(unsigned) byte, word or string required"
            return False, "incompatible value for assignment"

    class MemMappedValue(Value):
        def __init__(self, address: int, datatype: DataType, length: int, name: str=None, constant: bool=False) -> None:
            super().__init__(datatype, name, constant)
            self.address = address
            self.length = length

        def __hash__(self):
            return hash((self.datatype, self.address, self.length, self.name))

        def __eq__(self, other: Any) -> bool:
            if not isinstance(other, ParseResult.MemMappedValue):
                return NotImplemented
            elif self is other:
                return True
            else:
                return other.datatype == self.datatype and other.address == self.address and \
                       other.length == self.length and other.name == self.name

        def __str__(self):
            return "<MemMappedValue ${:04x} type={:s} #={:d} name={} constant={}>"\
                .format(self.address, self.datatype, self.length, self.name, self.constant)

        def assignable_from(self, other: 'ParseResult.Value') -> Tuple[bool, str]:
            if self.constant:
                return False, "cannot assign to a constant"
            if isinstance(other, ParseResult.PlaceholderSymbol):
                return True, ""
            elif self.datatype in (DataType.BYTE, DataType.WORD, DataType.FLOAT):
                if isinstance(other, (ParseResult.IntegerValue, ParseResult.FloatValue)):
                    range_error = check_value_in_range(self.datatype, "", 1, other.value)
                    if range_error:
                        return False, range_error
                    return True, ""
                elif isinstance(other, ParseResult.RegisterValue):
                    if other.datatype == DataType.BYTE:
                        if self.datatype in (DataType.BYTE, DataType.WORD, DataType.FLOAT):
                            return True, ""
                        return False, "can't assign register to this"
                    elif other.datatype == DataType.WORD:
                        if self.datatype in (DataType.WORD, DataType.FLOAT):
                            return True, ""
                        return False, "can't assign 16 bit combined registers to byte"
                elif isinstance(other, ParseResult.StringValue):
                    if self.datatype == DataType.WORD:
                        return True, ""
                    return False, "string address requires 16 bits (a word)"
                if self.datatype == DataType.BYTE:
                    return False, "(unsigned) byte required"
                if self.datatype == DataType.WORD:
                    return False, "(unsigned) word required"
            return False, "incompatible value for assignment"

    class _Stmt:
        def resolve_symbol_references(self, parser: 'Parser', cur_block: 'ParseResult.Block',
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

        def resolve_symbol_references(self, parser: 'Parser', cur_block: 'ParseResult.Block',
                                      stmt_index: int, statements: List['ParseResult._Stmt']) -> None:
            if isinstance(self.right, ParseResult.PlaceholderSymbol):
                value = parser.parse_expression(self.right.name, cur_block)
                if isinstance(value, ParseResult.PlaceholderSymbol):
                    raise ParseError(cur_block.sourcefile, cur_block.linenum, "", "cannot resolve symbol: " + self.right.name)
                self.right = value
            lv_resolved = []
            for lv in self.leftvalues:
                if isinstance(lv, ParseResult.PlaceholderSymbol):
                    value = parser.parse_expression(lv.name, cur_block)
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
                assignable, reason = lv.assignable_from(self.right)
                if not assignable:
                    raise ParseError(cur_block.sourcefile, cur_block.linenum, "",
                                     "cannot assign {0} to {1}; {2}".format(self.right, lv, reason))

        _immediate_string_vars = {}   # type: Dict[str, Tuple[str, str]]

        def desugar_immediate_string(self, cur_block: 'ParseResult.Block') -> None:
            if self.right.name or not isinstance(self.right, ParseResult.StringValue):
                return
            if self.right.value in self._immediate_string_vars:
                blockname, stringvar_name = self._immediate_string_vars[self.right.value]
                if blockname:
                    self.right.name = blockname + "." + stringvar_name
                else:
                    self.right.name = stringvar_name
            else:
                stringvar_name = "il65_str_{:d}".format(id(self))
                cur_block.symbols.define_variable(cur_block.name, stringvar_name, cur_block.sourcefile, 0, DataType.STRING,
                                                  value=self.right.value)
                self.right.name = stringvar_name
                self._immediate_string_vars[self.right.value] = (cur_block.name, stringvar_name)

    class ReturnStmt(_Stmt):
        def __init__(self, a: Optional['ParseResult.Value']=None,
                     x: Optional['ParseResult.Value']=None,
                     y: Optional['ParseResult.Value']=None) -> None:
            self.a = a
            self.x = x
            self.y = y

        def resolve_symbol_references(self, parser: 'Parser', cur_block: 'ParseResult.Block',
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

        def resolve_symbol_references(self, parser: 'Parser', cur_block: 'ParseResult.Block',
                                      stmt_index: int, statements: List['ParseResult._Stmt']) -> None:
            if isinstance(self.what, ParseResult.PlaceholderSymbol):
                value = parser.parse_expression(self.what.name, cur_block)
                if isinstance(value, ParseResult.PlaceholderSymbol):
                    raise ParseError(cur_block.sourcefile, cur_block.linenum, "", "cannot resolve symbol: " + self.what.name)
                self.what = value

    class CallStmt(_Stmt):
        def __init__(self, line_number: int, address: Optional[int]=None, unresolved: str=None,
                     is_goto: bool=False, preserve_regs: bool=True) -> None:
            self.address = address
            self.subroutine = None      # type: SubroutineDef
            self.unresolved = unresolved
            self.is_goto = is_goto
            self.preserve_regs = preserve_regs
            self.call_module = ""
            self.call_label = ""
            self.line_number = line_number

        def resolve_symbol_references(self, parser: 'Parser', cur_block: 'ParseResult.Block',
                                      stmt_index: int, statements: List['ParseResult._Stmt']) -> None:
            if self.unresolved:
                symblock, identifier = parser.result.lookup_symbol(self.unresolved, cur_block)
                if not identifier:
                    sourceline = [l[1] for l in parser.lines if l[0] == self.line_number][0]
                    raise ParseError(cur_block.sourcefile, self.line_number, sourceline, "unknown symbol '{:s}'".format(self.unresolved))
                if isinstance(identifier, SubroutineDef):
                    self.subroutine = identifier
                if cur_block is symblock:
                    self.call_module, self.call_label = "", identifier.name
                else:
                    self.call_module = symblock.label
                self.call_label = identifier.name
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
        self.start_address = 0
        self.blocks = []          # type: List['ParseResult.Block']

    def add_block(self, block: 'ParseResult.Block', position: Optional[int]=None) -> None:
        if position is not None:
            self.blocks.insert(position, block)
        else:
            self.blocks.append(block)

    def merge(self, parsed: 'ParseResult') -> None:
        self.blocks.extend(parsed.blocks)

    def lookup_symbol(self, name: str, localblock: Block) -> Tuple[Optional[Block], Optional[SymbolDefinition]]:
        # search for a symbol. Returns (containing_block, symbol) if found, else (None, None).
        name1, sep, name2 = name.partition(".")
        if sep:
            for b in self.blocks:
                if b.name == name1:
                    if name2 in b.symbols:
                        return b, b.symbols[name2]
                    return None, None
        elif name1 in localblock.symbols:
            return localblock, localblock.symbols[name1]
        return None, None


class Parser:
    def __init__(self, sourcefile: str, outputdir: str,
                 sourcecode: Optional[str]=None, zeropage: Zeropage=None, parsing_import: bool=False) -> None:
        self.result = ParseResult(sourcefile)
        self.zeropage = zeropage
        self.sourcefile = sourcefile
        self.outputdir = outputdir
        self.parsing_import = parsing_import     # are we parsing a import file?
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
            if self.parsing_import:
                print("Error (in imported file):", str(x))
            else:
                print("Error:", str(x))
            if x.sourceline:
                print("\tsource text: '{:s}'".format(x.sourceline))
            raise   # XXX temporary solution to get stack trace info in the event of parse errors
            return None

    def _parse(self) -> ParseResult:
        print("\nparsing (pass 1)", self.sourcefile)
        self.parse_header()
        if not self.zeropage:
            self.zeropage = Zeropage(self.result.clobberzp)
        while True:
            next_line = self.peek_next_line()[1]
            if next_line.lstrip().startswith("~"):
                block = self.parse_block()
                if block:
                    self.result.add_block(block)
            elif next_line.lstrip().startswith("import"):
                parsed_import = self.parse_import()
                if parsed_import:
                    self.result.merge(parsed_import)
                else:
                    raise self.PError("Error while parsing imported file")
            else:
                break
        _, line = self.next_line()
        if line:
            raise self.PError("invalid statement or characters, block expected")
        if not self.parsing_import:
            # check if we have a proper main block to contain the program's entry point
            for block in self.result.blocks:
                if block.name == "main":
                    if "start" not in block.label_names:
                        self.cur_linenum = block.linenum
                        raise self.PError("The 'main' block should contain the program entry point 'start'")
                    if not any(s for s in block.statements if isinstance(s, ParseResult.ReturnStmt)):
                        print("warning: {:s}:{:d}: The 'main' block is lacking a return statement.".format(self.sourcefile, block.linenum))
                    break
            else:
                raise self.PError("A block named 'main' should be defined for the program's entry point 'start'")
        # parsing pass 2
        print("\nparsing (pass 2)", self.sourcefile)
        # fix up labels that are unknown, and desugar immediate string value assignments:
        for block in self.result.blocks:
            statements = list(block.statements)
            for index, stmt in enumerate(statements):
                try:
                    stmt.resolve_symbol_references(self, block, index, statements)
                except LookupError as x:
                    self.cur_linenum = block.linenum
                    raise self.PError("Symbol reference error in this block") from x
                if isinstance(stmt, ParseResult.AssignmentStmt):
                    stmt.desugar_immediate_string(block)
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
        output_specified = False
        while True:
            num, line = self.next_line()
            if line.startswith("output"):
                if output_specified:
                    raise self.PError("multiple occurrences of 'output'")
                output_specified = True
                _, _, arg = line.partition(" ")
                arg = arg.lstrip()
                self.result.with_sys = False
                self.result.format = ProgramFormat.RAW
                if arg == "raw":
                    pass
                elif arg == "prg":
                    self.result.format = ProgramFormat.PRG
                elif arg.replace(' ', '') == "prg,sys":
                    self.result.with_sys = True
                    self.result.format = ProgramFormat.PRG
                else:
                    raise self.PError("invalid output format")
            elif line.startswith("clobberzp"):
                if self.result.clobberzp:
                    raise self.PError("multiple occurrences of 'clobberzp'")
                self.result.clobberzp = True
                _, _, arg = line.partition(" ")
                arg = arg.lstrip()
                if arg == "restore":
                    self.result.restorezp = True
                elif arg == "":
                    pass
                else:
                    raise self.PError("invalid arg for clobberzp")
            elif line.startswith("address"):
                if self.result.start_address:
                    raise self.PError("multiple occurrences of 'address'")
                _, _, arg = line.partition(" ")
                self.result.start_address = self.parse_integer(arg)
                if self.result.format == ProgramFormat.PRG and self.result.with_sys and self.result.start_address != 0x0801:
                    raise self.PError("cannot use non-default 'address' when output format includes basic SYS program")
            else:
                # header parsing finished!
                self.prev_line()
                if not self.result.start_address:
                    # set the proper default start address
                    if self.result.format == ProgramFormat.PRG:
                        self.result.start_address = 0x0801  # normal C-64 basic program start address
                    elif self.result.format == ProgramFormat.RAW:
                        self.result.start_address = 0xc000  # default start for raw assembly
                if self.result.format == ProgramFormat.PRG and self.result.with_sys and self.result.start_address != 0x0801:
                    raise self.PError("cannot use non-default 'address' when output format includes basic SYS program")
                return

    def parse_import(self) -> ParseResult:
        num, line = self.next_line()
        line = line.lstrip()
        if not line.startswith("import"):
            raise self.PError("expected import")
        try:
            _, arg = line.split(maxsplit=1)
        except ValueError:
            raise self.PError("invalid import statement")
        if not arg.startswith('"') or not arg.endswith('"'):
            raise self.PError("filename must be between quotes")
        filename = arg[1:-1]
        if not filename:
            raise self.PError("invalid filename")
        filename_at_source_location = os.path.join(os.path.split(self.sourcefile)[0], filename)
        filename_at_libs_location = os.path.join(os.path.split(sys.argv[0])[0], "lib", filename)
        candidates = [filename,
                      filename_at_source_location,
                      filename_at_libs_location,
                      filename+".ill",
                      filename_at_source_location+".ill",
                      filename_at_libs_location+".ill"]
        for filename in candidates:
            if os.path.isfile(filename):
                parser = Parser(filename, self.outputdir, zeropage=self.zeropage, parsing_import=True)
                print("importing", filename)
                return parser.parse()
        raise self.PError("imported file not found")

    def parse_block(self) -> ParseResult.Block:
        # first line contains block header "~ [name] [addr]" followed by a '{'
        num, line = self.next_line()
        line = line.lstrip()
        if not line.startswith("~"):
            raise self.PError("expected '~' (block)")
        self.cur_block = ParseResult.Block(self.sourcefile, num, self.zeropage)
        block_args = line[1:].split()
        arg = ""
        is_zp_block = False
        while block_args:
            arg = block_args.pop(0)
            if arg.isidentifier():
                print("  parsing block '" + arg + "'")
                if arg.lower() == "zeropage" or arg in ("zp", "zP", "Zp"):
                    raise self.PError("zero page block should be named 'ZP'")
                is_zp_block = arg == "ZP"
                if arg in set(b.name for b in self.result.blocks):
                    orig = [b for b in self.result.blocks if b.name == arg][0]
                    if not is_zp_block:
                        raise self.PError("duplicate block name '{0:s}', original definition at {1:s} line {2:d}"
                                          .format(arg, orig.sourcefile, orig.linenum))
                    self.cur_block = orig  # zero page block occurrences are merged
                else:
                    self.cur_block.name = arg
            elif arg == "{":
                break
            elif arg.endswith("{"):
                # when there is no whitespace before the {
                block_args.insert(0, "{")
                block_args.insert(0, arg[:-1])
                continue
            else:
                try:
                    block_address = self.parse_integer(arg)
                except ParseError:
                    raise self.PError("Invalid number or block name")
                if block_address == 0 or (block_address < 0x0200 and not is_zp_block):
                    raise self.PError("block address must be >= $0200 (or omitted)")
                if is_zp_block:
                    if block_address not in (0, 0x04):
                        raise self.PError("zero page block address must be $04 (or omittted)")
                    block_address = 0x04
                self.cur_block.address = block_address
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
                if is_zp_block and any(b.name == "ZP" for b in self.result.blocks):
                    return None     # we already have the ZP block
                return self.cur_block
            if line.startswith("var"):
                self.parse_var_def(line)
            elif line.startswith("const"):
                self.parse_const_def(line)
            elif line.startswith("memory"):
                self.parse_memory_def(line, is_zp_block)
            elif line.startswith("subx"):
                if is_zp_block:
                    raise self.PError("ZP block cannot contain subroutines")
                self.parse_subx_def(line)
            elif line.startswith(("asminclude", "asmbinary")):
                if is_zp_block:
                    raise self.PError("ZP block cannot contain assembler directives")
                self.cur_block.statements.append(self.parse_asminclude(line))
            elif line.startswith("asm"):
                if is_zp_block:
                    raise self.PError("ZP block cannot contain code statements")
                self.prev_line()
                self.cur_block.statements.append(self.parse_asm())
                continue
            elif unstripped_line.startswith((" ", "\t")):
                if is_zp_block:
                    raise self.PError("ZP block cannot contain code statements")
                self.cur_block.statements.append(self.parse_statement(line))
                continue
            elif line:
                if is_zp_block:
                    raise self.PError("ZP block cannot contain code labels")
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

    def parse_memory_def(self, line: str, is_zeropage: bool=False) -> None:
        dotargs = self.psplit(line)
        if dotargs[0] != "memory" or len(dotargs) not in (3, 4):
            raise self.PError("invalid memory definition")
        msize = 1
        mtype = DataType.BYTE
        memtype = dotargs[1]
        matrixsize = None
        if memtype.startswith("."):
            if memtype == ".byte":
                pass
            elif memtype == ".word":
                msize = 2
                mtype = DataType.WORD
            elif memtype == ".float":
                msize = 5   # 5-byte cbm MFLPT format, this is the only float format supported for now
                mtype = DataType.FLOAT
            elif memtype.startswith(".array(") and memtype.endswith(")"):
                msize = self._size_from_arraydecl(memtype)
                mtype = DataType.BYTEARRAY
            elif memtype.startswith(".wordarray(") and memtype.endswith(")"):
                msize = self._size_from_arraydecl(memtype)
                mtype = DataType.WORDARRAY
            elif memtype.startswith(".matrix(") and memtype.endswith(")"):
                if len(dotargs) != 4:
                    raise self.PError("missing matrix memory address")
                matrixsize = self._size_from_matrixdecl(memtype)
                msize = matrixsize[0] * matrixsize[1]
                mtype = DataType.MATRIX
            else:
                raise self.PError("invalid memory type")
            dotargs.pop(1)
        if len(dotargs) < 3:
            raise self.PError("invalid memory definition")
        varname = dotargs[1]
        if not varname.isidentifier():
            raise self.PError("invalid symbol name")
        if varname in RESERVED_NAMES:
            raise self.PError("can't use a reserved name here")
        memaddress = self.parse_integer(dotargs[2])
        if is_zeropage and memaddress > 0xff:
            raise self.PError("address must lie in zeropage $00-$ff")
        try:
            self.cur_block.symbols.define_variable(self.cur_block.name, varname,
                                                   self.sourcefile, self.cur_linenum, mtype,
                                                   length=msize, address=memaddress, matrixsize=matrixsize)
        except SymbolError as x:
            raise self.PError(str(x)) from x

    def parse_const_def(self, line: str) -> None:
        dotargs = self.psplit(line)
        if dotargs[0] != "const" or len(dotargs) not in (3, 4):
            raise self.PError("invalid const definition")
        if len(dotargs) == 4:
            # 'const .datatype symbolname expression'
            if dotargs[1] == ".byte":
                datatype = DataType.BYTE
            elif dotargs[1] == ".word":
                datatype = DataType.WORD
            elif dotargs[1] == ".float":
                datatype = DataType.FLOAT
            elif dotargs[1] == ".text":
                datatype = DataType.STRING
            elif dotargs[1] == ".ptext":
                datatype = DataType.STRING_P
            elif dotargs[1] == ".stext":
                datatype = DataType.STRING_S
            elif dotargs[1] == ".pstext":
                datatype = DataType.STRING_PS
            else:
                raise self.PError("invalid const datatype")
            varname = dotargs[2]
            value = dotargs[3]
        else:
            # 'const symbolname expression'
            datatype = DataType.BYTE
            varname = dotargs[1]
            if varname[0] == ".":
                raise self.PError("invalid const definition, missing constant name or value?")
            value = dotargs[2]
        if not varname.isidentifier():
            raise self.PError("invalid symbol name")
        if varname in RESERVED_NAMES:
            raise self.PError("can't use a reserved name here")
        else:
            constvalue = self.parse_primitive_value(value)
            try:
                self.cur_block.symbols.define_constant(self.cur_block.name, varname,
                                                       self.sourcefile, self.cur_linenum, datatype, value=constvalue)
            except (ValueError, SymbolError) as x:
                raise self.PError(str(x)) from x

    def parse_subx_def(self, line: str) -> None:
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
        address = self.parse_integer(address_str)
        self.cur_block.symbols.define_sub(self.cur_block.name, name,
                                          self.sourcefile, self.cur_linenum, parameters, results, address)

    def parse_var_def(self, line: str) -> None:
        match = re.match(r"^var\s+.(?P<type>(?:s|p|ps|)text)\s+(?P<name>\w+)\s+(?P<value>['\"].+['\"])$", line)
        if match:
            # it's a var string definition.
            datatype = {
                "text": DataType.STRING,
                "ptext": DataType.STRING_P,
                "stext": DataType.STRING_S,
                "pstext": DataType.STRING_PS
            }[match.group("type")]
            vname = match.group("name")
            if vname in RESERVED_NAMES:
                raise self.PError("can't use a reserved name here")
            strvalue = self.parse_string(match.group("value"))
            try:
                self.cur_block.symbols.define_variable(self.cur_block.name, vname,
                                                       self.sourcefile, self.cur_linenum, datatype, value=strvalue)
            except SymbolError as x:
                raise self.PError(str(x)) from x
            return

        args = self.psplit(line)
        if args[0] != "var" or len(args) < 2 or len(args) > 5:
            raise self.PError("invalid var decl (1)")

        def get_datatype(datatype: str) -> Tuple[DataType, Union[int, Tuple[int, int]]]:
            if datatype == ".byte":
                return DataType.BYTE, 1
            elif datatype == ".word":
                return DataType.WORD, 1
            elif datatype == ".float":
                return DataType.FLOAT, 1
            elif datatype.startswith(".array(") and datatype.endswith(")"):
                return DataType.BYTEARRAY, self._size_from_arraydecl(datatype)
            elif datatype.startswith(".wordarray(") and datatype.endswith(")"):
                return DataType.WORDARRAY, self._size_from_arraydecl(datatype)
            elif datatype.startswith(".matrix(") and datatype.endswith(")"):
                return DataType.MATRIX, self._size_from_matrixdecl(datatype)
            else:
                raise self.PError("invalid data type: " + datatype)

        vaddr = None
        value = 0    # type: Union[int, float, str]
        matrixsize = None  # type: Tuple[int, int]
        if len(args) == 2:  # var uninit_bytevar
            vname = args[1]
            if not vname.isidentifier():
                raise self.PError("invalid variable name")
            if vname in REGISTER_SYMBOLS:
                raise self.PError("cannot use a register name as variable")
            datatype = DataType.BYTE
            vlen = 1
        elif len(args) == 3:  # var datatype varname, OR var varname expression
            if args[1][0] != '.':
                # assume var varname expression
                vname = args[1]
                if not vname.isidentifier():
                    raise self.PError("invalid variable name, or maybe forgot variable type")
                datatype, vlen = DataType.BYTE, 1
                value = self.parse_primitive_value(args[2])
            else:
                # assume var datatype varname
                datatype, vlen = get_datatype(args[1])   # type: ignore
                vname = args[2]
        elif len(args) == 4:  # var datatype varname expression
            vname = args[2]
            if not vname.isidentifier():
                raise self.PError("invalid variable name, or var syntax")
            datatype, vlen = get_datatype(args[1])   # type: ignore
            value = self.parse_primitive_value(args[3])
        else:
            raise self.PError("invalid var decl (2)")
        if datatype == DataType.MATRIX:
            matrixsize = vlen   # type: ignore
            vlen = None
        if vname in RESERVED_NAMES:
            raise self.PError("can't use a reserved name here")
        try:
            self.cur_block.symbols.define_variable(self.cur_block.name, vname,
                                                   self.sourcefile, self.cur_linenum, datatype,
                                                   address=vaddr, length=vlen, value=value, matrixsize=matrixsize)
        except (ValueError, SymbolError) as x:
            raise self.PError(str(x)) from x

    def parse_statement(self, line: str) -> ParseResult._Stmt:
        lhs, sep, rhs = line.partition("=")
        if sep:
            return self.parse_assignment(line)
        elif line.startswith("return"):
            return self.parse_return(line)
        elif line.endswith(("++", "--")):
            incr = line.endswith("++")
            what = self.parse_expression(line[:-2].rstrip())
            if isinstance(what, ParseResult.IntegerValue):
                raise self.PError("cannot in/decrement a constant value")
            return ParseResult.IncrDecrStmt(what, 1 if incr else -1)
        elif line.startswith("call"):
            return self.parse_call_or_go(line, "call")
        elif line.startswith("fcall"):
            return self.parse_call_or_go(line, "fcall")
        elif line.startswith("go"):
            return self.parse_call_or_go(line, "go")
        else:
            raise self.PError("invalid statement")

    def parse_call_or_go(self, line: str, what: str) -> ParseResult.CallStmt:
        args = line.split()
        if len(args) != 2:
            raise self.PError("invalid call/go arguments")
        if what == "go":
            return ParseResult.CallStmt(self.cur_linenum, unresolved=args[1], is_goto=True)
        elif what == "call":
            return ParseResult.CallStmt(self.cur_linenum, unresolved=args[1], is_goto=False)
        elif what == "fcall":
            return ParseResult.CallStmt(self.cur_linenum, unresolved=args[1], is_goto=False, preserve_regs=False)
        else:
            raise ValueError("invalid what")

    def parse_assignment(self, line: str) -> ParseResult.AssignmentStmt:
        # parses assigning a value to one or more targets
        parts = line.split("=")
        rhs = parts.pop()
        l_values = [self.parse_expression(part) for part in parts]
        if any(isinstance(lv, ParseResult.IntegerValue) for lv in l_values):
            raise self.PError("can't have a constant as assignment target, did you mean [name] instead?")
        r_value = self.parse_expression(rhs)
        for lv in l_values:
            assignable, reason = lv.assignable_from(r_value)
            if not assignable:
                raise self.PError("cannot assign {0} to {1}; {2}".format(r_value, lv, reason))
            if lv.datatype in (DataType.BYTE, DataType.WORD, DataType.MATRIX):
                if isinstance(r_value, ParseResult.FloatValue):
                    trunc_float_if_needed(self.sourcefile, self.cur_linenum, lv.datatype, r_value.value)  # for the warning
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
            a = self.parse_expression(values[0]) if values[0] else None
            if len(values) > 1:
                x = self.parse_expression(values[1]) if values[1] else None
                if len(values) > 2:
                    y = self.parse_expression(values[2]) if values[2] else None
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

    def parse_asminclude(self, line: str) -> ParseResult.InlineAsm:
        aline = line.split()
        if len(aline) < 2:
            raise self.PError("invalid asminclude or asmbinary statement")
        filename = aline[1]
        if not filename.startswith('"') or not filename.endswith('"'):
            raise self.PError("filename must be between quotes")
        filename = filename[1:-1]
        if not filename:
            raise self.PError("invalid filename")
        filename_in_sourcedir = os.path.join(os.path.split(self.sourcefile)[0], filename)
        filename_in_output_location = os.path.join(self.outputdir, filename)
        if not os.path.isfile(filename_in_sourcedir):
            raise self.PError("included file not found")
        print("copying included file to output location:", filename)
        shutil.copy(filename_in_sourcedir, filename_in_output_location)
        if aline[0] == "asminclude":
            if len(aline) == 3:
                scopename = aline[2]
                lines = ['{:s}\t.binclude "{:s}"'.format(scopename, filename)]
            else:
                raise self.PError("invalid asminclude statement")
            return ParseResult.InlineAsm(self.cur_linenum, lines)
        elif aline[0] == "asmbinary":
            if len(aline) == 4:
                offset = self.parse_integer(aline[2])
                length = self.parse_integer(aline[3])
                lines = ['\t.binary "{:s}", ${:04x}, ${:04x}'.format(filename, offset, length)]
            elif len(aline) == 3:
                offset = self.parse_integer(aline[2])
                lines = ['\t.binary "{:s}", ${:04x}'.format(filename, offset)]
            elif len(aline) == 2:
                lines = ['\t.binary "{:s}"'.format(filename)]
            else:
                raise self.PError("invalid asmbinary statement")
            return ParseResult.InlineAsm(self.cur_linenum, lines)
        else:
            raise self.PError("invalid statement")

    def parse_expression(self, text: str, cur_block: Optional[ParseResult.Block]=None) -> ParseResult.Value:
        # parse an expression into whatever it is (primitive value, register, memory, register, etc)
        cur_block = cur_block or self.cur_block
        text = text.strip()
        if not text:
            raise self.PError("value expected")
        if text[0] == '^':
            # take the pointer (memory address) from the thing that follows this
            expression = self.parse_expression(text[1:], cur_block)
            if isinstance(expression, ParseResult.StringValue):
                return expression
            elif isinstance(expression, ParseResult.MemMappedValue):
                return ParseResult.IntegerValue(expression.address, datatype=DataType.WORD, name=expression.name)
            elif isinstance(expression, ParseResult.PlaceholderSymbol):
                raise self.PError("cannot take the address from an unresolved symbol")
            else:
                raise self.PError("cannot take the address from this type")
        elif text[0] in "-.0123456789$%":
            number = self.parse_number(text)
            try:
                if type(number) is int:
                    return ParseResult.IntegerValue(int(number))
                elif type(number) is float:
                    return ParseResult.FloatValue(number)
                else:
                    raise TypeError("invalid number type")
            except (ValueError, OverflowError) as ex:
                raise self.PError(str(ex))
        elif text in REGISTER_WORDS:
            return ParseResult.RegisterValue(text, DataType.WORD)
        elif text in REGISTER_BYTES:
            return ParseResult.RegisterValue(text, DataType.BYTE)
        elif (text.startswith("'") and text.endswith("'")) or (text.startswith('"') and text.endswith('"')):
            strvalue = self.parse_string(text)
            if len(strvalue) == 1:
                petscii_code = self.char_to_bytevalue(strvalue)
                return ParseResult.IntegerValue(petscii_code)
            return ParseResult.StringValue(strvalue)
        elif text == "true":
            return ParseResult.IntegerValue(1)
        elif text == "false":
            return ParseResult.IntegerValue(0)
        elif self.is_identifier(text):
            symblock, sym = self.result.lookup_symbol(text, cur_block)
            if sym is None:
                # symbols is not (yet) known, store a placeholder to resolve later in parse pass 2
                return ParseResult.PlaceholderSymbol(None, text)
            elif isinstance(sym, (VariableDef, ConstantDef)):
                constant = isinstance(sym, ConstantDef)
                if cur_block is symblock:
                    symbolname = sym.name
                else:
                    symbolname = "{:s}.{:s}".format(sym.blockname, sym.name)
                if isinstance(sym, VariableDef) and sym.register:
                    return ParseResult.RegisterValue(sym.register, sym.type, name=symbolname)
                elif sym.type in (DataType.BYTE, DataType.WORD, DataType.FLOAT):
                    if isinstance(sym, ConstantDef):
                        symbolvalue = sym.value or 0
                    else:
                        symbolvalue = sym.address or 0
                    if type(symbolvalue) is int:
                        return ParseResult.MemMappedValue(int(symbolvalue), sym.type, sym.length, name=symbolname, constant=constant)
                    else:
                        raise TypeError("integer symbol required")
                elif sym.type in STRING_DATATYPES:
                    return ParseResult.StringValue(sym.value, name=symbolname, constant=constant)      # type: ignore
                elif sym.type == DataType.MATRIX:
                    raise self.PError("cannot manipulate matrix directly, use one of the matrix procedures")
                elif sym.type == DataType.BYTEARRAY or sym.type == DataType.WORDARRAY:
                    raise self.PError("cannot manipulate array directly, use one of the array procedures")
                else:
                    raise self.PError("invalid symbol type (1)")
            else:
                raise self.PError("invalid symbol type (2)")
        elif text.startswith('[') and text.endswith(']'):
            num_or_name = text[1:-1].strip()
            if num_or_name.isidentifier():
                try:
                    sym = cur_block.symbols[num_or_name]    # type: ignore
                except KeyError:
                    raise self.PError("unknown symbol (2): " + num_or_name)
                if isinstance(sym, ConstantDef):
                    if type(sym.value) is int:
                        return ParseResult.MemMappedValue(int(sym.value), sym.type, length=sym.length, name=sym.name)
                    else:
                        raise TypeError("integer required")
                else:
                    raise self.PError("invalid symbol type used as lvalue of assignment (3)")
            else:
                if num_or_name.endswith(".word"):
                    addr = self.parse_integer(num_or_name[:-5])
                    return ParseResult.MemMappedValue(addr, DataType.WORD, length=1)
                elif num_or_name.endswith(".float"):
                    addr = self.parse_integer(num_or_name[:-6])
                    return ParseResult.MemMappedValue(addr, DataType.FLOAT, length=1)
                else:
                    addr = self.parse_integer(num_or_name)
                    return ParseResult.MemMappedValue(addr, DataType.BYTE, length=1)
        else:
            raise self.PError("invalid value '" + text + "'")

    def is_identifier(self, name: str) -> bool:
        if name.isidentifier():
            return True
        blockname, sep, name = name.partition(".")
        if sep:
            return blockname.isidentifier() and name.isidentifier()
        return False

    def parse_integer(self, number: str) -> int:
        # parse a numeric string into an actual integer
        number = number.lstrip()
        try:
            if number[0] in "0123456789":
                return int(number)
            elif number.startswith(("$", "0x")):
                return int(number[1:], 16)
            elif number.startswith("%"):
                return int(number[1:], 2)
            else:
                raise self.PError("invalid number")
        except ValueError as vx:
            raise self.PError("invalid number; "+str(vx))

    def parse_number(self, text: str) -> Union[int, float]:
        # parse string into an int or float
        try:
            return self.parse_integer(text)
        except (ValueError, ParseError):
            if text == "true":
                return 1
            elif text == "false":
                return 0
            elif text[0] in "-.0123456789":
                flt = float(text)
                if FLOAT_MAX_NEGATIVE <= flt <= FLOAT_MAX_POSITIVE:
                    return flt
                raise self.PError("floating point number too large to be stored in 5-byte cbm MFLPT format")
            else:
                raise self.PError("invalid number")

    def parse_string(self, text: str) -> str:
        if text.startswith("'") and not text.endswith("'") or text.startswith('"') and not text.endswith('"'):
            raise self.PError("mismatched string quotes")
        return ast.literal_eval(text)

    def _size_from_arraydecl(self, decl: str) -> int:
        return self.parse_integer(decl[:-1].split("(")[-1])

    def _size_from_matrixdecl(self, decl: str) -> Tuple[int, int]:
        dimensions = decl[:-1].split("(")[-1]
        try:
            xs, ys = dimensions.split(",")
        except ValueError:
            raise self.PError("invalid matrix dimensions")
        return self.parse_integer(xs), self.parse_integer(ys)

    def psplit(self, sentence: str, separators: str=" \t", lparen: str="(", rparen: str=")") -> List[str]:
        """split a sentence but not on separators within parenthesis"""
        nb_brackets = 0
        sentence = sentence.strip(separators)  # get rid of leading/trailing seps
        indices = [0]
        for i, c in enumerate(sentence):
            if c == lparen:
                nb_brackets += 1
            elif c == rparen:
                nb_brackets -= 1
            elif c in separators and nb_brackets == 0:
                indices.append(i)
            # handle malformed string
            if nb_brackets < 0:
                raise self.PError("syntax error")

        indices.append(len(sentence))
        # handle missing closing parentheses
        if nb_brackets > 0:
            raise self.PError("syntax error")
        result = [sentence[i:j].strip(separators) for i, j in zip(indices, indices[1:])]
        return list(filter(None, result))   # remove empty strings

    def parse_primitive_value(self, text: str) -> Union[int, float, str]:
        # parses a primitive value (integer, float or string)
        try:
            return self.parse_number(text)
        except ParseError:
            if text[0] == "'" and text[-1] == "'" or text[0] == '"' and text[-1] == '"':
                if len(text) == 3:
                    return self.char_to_bytevalue(text[1])
                else:
                    return self.parse_string(text)
            raise

    def char_to_bytevalue(self, character: str, petscii: bool=True) -> int:
        assert len(character) == 1
        if petscii:
            return ord(character.translate(ascii_to_petscii_trans))
        else:
            raise NotImplementedError("screencode conversion not yet implemented for chars")


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


# ASCII/UNICODE-to-PETSCII translation table
# Unicode symbols supported that map to a PETSCII character:
#   £ ↑ ⬆ ← ⬅ ♠ ♥ ♦ ♣ π ● ○
ascii_to_petscii_trans = str.maketrans({
    '\f': 147,  # form feed becomes ClearScreen
    '\n': 13,   # line feed becomes a RETURN
    '\r': 17,   # CR becomes CursorDown
    'a': 65,
    'b': 66,
    'c': 67,
    'd': 68,
    'e': 69,
    'f': 70,
    'g': 71,
    'h': 72,
    'i': 73,
    'j': 74,
    'k': 75,
    'l': 76,
    'm': 77,
    'n': 78,
    'o': 79,
    'p': 80,
    'q': 81,
    'r': 82,
    's': 83,
    't': 84,
    'u': 85,
    'v': 86,
    'w': 87,
    'x': 88,
    'y': 89,
    'z': 90,
    'A': 97,
    'B': 98,
    'C': 99,
    'D': 100,
    'E': 101,
    'F': 102,
    'G': 103,
    'H': 104,
    'I': 105,
    'J': 106,
    'K': 107,
    'L': 108,
    'M': 109,
    'N': 110,
    'O': 111,
    'P': 112,
    'Q': 113,
    'R': 114,
    'S': 115,
    'T': 116,
    'U': 117,
    'V': 118,
    'W': 119,
    'X': 120,
    'Y': 121,
    'Z': 122,
    '{': 179,       # left squiggle
    '}': 235,       # right squiggle
    '£': 92,        # pound currency sign
    '^': 94,        # up arrow
    '~': 126,       # pi math symbol
    'π': 126,       # pi symbol
    '|': 221,       # vertical bar
    '↑': 94,        # up arrow
    '⬆': 94,        # up arrow
    '←': 95,        # left arrow
    '⬅': 95,        # left arrow
    '_': 164,       # lower bar/underscore
    '`': 39,        # single quote
    '♠': 97,        # spades
    '●': 113,       # circle
    '♥': 115,       # hearts
    '○': 119,       # open circle
    '♣': 120,       # clubs
    '♦': 122,       # diamonds

    # @todo add more unicode petscii equivalents see http://style64.org/petscii/  also add them to pyc65
})
