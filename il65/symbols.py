"""
Intermediate Language for 6502/6510 microprocessors
Here are the symbol (name) operations such as lookups, datatype definitions.

Written by Irmen de Jong (irmen@razorvine.net)
License: GNU GPL 3.0, see LICENSE
"""

import inspect
import math
import enum
from functools import total_ordering
from typing import Optional, Set, Union, Tuple, Dict, Iterable, Sequence, Any, List


REGISTER_SYMBOLS = {"A", "X", "Y", "AX", "AY", "XY", "SC"}
REGISTER_SYMBOLS_RETURNVALUES = REGISTER_SYMBOLS - {"SC"}
REGISTER_BYTES = {"A", "X", "Y", "SC"}
REGISTER_WORDS = {"AX", "AY", "XY"}

# 5-byte cbm MFLPT format limitations:
FLOAT_MAX_POSITIVE = 1.7014118345e+38
FLOAT_MAX_NEGATIVE = -1.7014118345e+38

RESERVED_NAMES = {"true", "false", "var", "memory", "const", "asm"}
RESERVED_NAMES |= REGISTER_SYMBOLS


@total_ordering
class DataType(enum.Enum):
    """The possible data types of values"""
    BYTE = 1
    WORD = 2
    FLOAT = 3
    BYTEARRAY = 4
    WORDARRAY = 5
    MATRIX = 6
    STRING = 7
    STRING_P = 8
    STRING_S = 9
    STRING_PS = 10

    def assignable_from_value(self, value: Union[int, float]) -> bool:
        if self == DataType.BYTE:
            return 0 <= value < 0x100
        if self == DataType.WORD:
            return 0 <= value < 0x10000
        if self == DataType.FLOAT:
            return type(value) in (float, int)
        return False

    def __lt__(self, other):
        if self.__class__ == other.__class__:
            return self.value < other.value
        return NotImplemented


STRING_DATATYPES = {DataType.STRING, DataType.STRING_P, DataType.STRING_S, DataType.STRING_PS}


class SymbolError(Exception):
    pass


_identifier_seq_nr = 0


class SymbolDefinition:
    def __init__(self, blockname: str, name: str, sourcefile: str, sourceline: int, allocate: bool) -> None:
        self.blockname = blockname
        self.name = name
        self.sourceref = "{:s}:{:d}".format(sourcefile, sourceline)
        self.allocate = allocate     # set to false if the variable is memory mapped (or a constant) instead of allocated
        global _identifier_seq_nr
        self.seq_nr = _identifier_seq_nr
        _identifier_seq_nr += 1

    def __lt__(self, other: 'SymbolDefinition') -> bool:
        if not isinstance(other, SymbolDefinition):
            return NotImplemented
        return (self.blockname, self.name, self.seq_nr) < (other.blockname, other.name, self.seq_nr)

    def __str__(self):
        return "<{:s} {:s}.{:s}>".format(self.__class__.__name__, self.blockname, self.name)


class LabelDef(SymbolDefinition):
    pass


class VariableDef(SymbolDefinition):
    # if address is None, it's a dynamically allocated variable.
    # if address is not None, it's a memory mapped variable (=memory address referenced by a name).
    def __init__(self, blockname: str, name: str, sourcefile: str, sourceline: int,
                 datatype: DataType, allocate: bool, *,
                 value: Union[int, float, str], length: int, address: Optional[int]=None,
                 register: str=None, matrixsize: Tuple[int, int]=None) -> None:
        super().__init__(blockname, name, sourcefile, sourceline, allocate)
        self.type = datatype
        self.address = address
        self.length = length
        self.value = value
        self.register = register
        self.matrixsize = matrixsize

    @property
    def is_memmap(self):
        return self.address is not None

    def __repr__(self):
        return "<Variable {:s}.{:s}, {:s}, addr {:s}, len {:s}, value {:s}>"\
            .format(self.blockname, self.name, self.type, str(self.address), str(self.length), str(self.value))

    def __lt__(self, other: 'SymbolDefinition') -> bool:
        if not isinstance(other, VariableDef):
            return NotImplemented
        v1 = (self.blockname, self.name or "", self.address or 0, self.seq_nr)
        v2 = (other.blockname, other.name or "", other.address or 0, self.seq_nr)
        return v1 < v2


class ConstantDef(SymbolDefinition):
    def __init__(self, blockname: str, name: str, sourcefile: str, sourceline: int, datatype: DataType, *,
                 value: Union[int, float, str], length: int) -> None:
        super().__init__(blockname, name, sourcefile, sourceline, False)
        self.type = datatype
        self.length = length
        self.value = value

    def __repr__(self):
        return "<Constant {:s}.{:s}, {:s}, len {:s}, value {:s}>"\
            .format(self.blockname, self.name, self.type, str(self.length), str(self.value))

    def __lt__(self, other: 'SymbolDefinition') -> bool:
        if not isinstance(other, ConstantDef):
            return NotImplemented
        v1 = (str(self.value) or "", self.blockname, self.name or "", self.seq_nr)
        v2 = (str(other.value) or "", other.blockname, other.name or "", self.seq_nr)
        return v1 < v2


class SubroutineDef(SymbolDefinition):
    def __init__(self, blockname: str, name: str, sourcefile: str, sourceline: int,
                 parameters: Sequence[Tuple[str, str]], returnvalues: Set[str], address: Optional[int]=None) -> None:
        super().__init__(blockname, name, sourcefile, sourceline, False)
        self.address = address
        self.parameters = parameters
        self.input_registers = set()        # type: Set[str]
        self.return_registers = set()       # type: Set[str]
        self.clobbered_registers = set()    # type: Set[str]
        for _, param in parameters:
            if param in REGISTER_BYTES:
                self.input_registers.add(param)
            elif param in REGISTER_WORDS:
                self.input_registers.add(param[0])
                self.input_registers.add(param[1])
            else:
                raise SymbolError("invalid parameter spec: " + param)
        for register in returnvalues:
            if register in REGISTER_SYMBOLS_RETURNVALUES:
                self.return_registers.add(register)
            elif len(register) == 2 and register[1] == '?' and register[0] in "AXY":
                self.clobbered_registers.add(register[0])
            else:
                raise SymbolError("invalid return value spec: " + register)


class Zeropage:
    SCRATCH_B1 = 0x02
    SCRATCH_B2 = 0x03

    def __init__(self) -> None:
        self.unused_bytes = []  # type: List[int]
        self.unused_words = []  # type: List[int]

    def configure(self, clobber_zp: bool = False) -> None:
        if clobber_zp:
            self.unused_bytes = list(range(0x04, 0x80))
            self.unused_words = list(range(0x80, 0x100, 2))
        else:
            # these are valid for the C-64:
            # ($02 and $03 are reserved as scratch addresses for various routines)
            self.unused_bytes = [0x06, 0x0a, 0x2a, 0x52, 0x93]  # 5 zp variables (8 bits each)
            self.unused_words = [0x04, 0xf7, 0xf9, 0xfb, 0xfd]  # 5 zp variables (16 bits each)
        assert self.SCRATCH_B1 not in self.unused_bytes and self.SCRATCH_B1 not in self.unused_words
        assert self.SCRATCH_B2 not in self.unused_bytes and self.SCRATCH_B2 not in self.unused_words

    def get_unused_byte(self):
        return self.unused_bytes.pop()

    def get_unused_word(self):
        return self.unused_words.pop()

    @property
    def available_byte_vars(self) -> int:
        return len(self.unused_bytes)

    @property
    def available_word_vars(self) -> int:
        return len(self.unused_words)


# the single, global Zeropage object
zeropage = Zeropage()


class SymbolTable:
    math_module_symbols = {name: definition for name, definition in vars(math).items() if not name.startswith("_")}

    def __init__(self, name: str, parent: Optional['SymbolTable'], owning_block: Any) -> None:
        self.name = name
        self.symbols = dict(SymbolTable.math_module_symbols)
        self.parent = parent
        self.owning_block = owning_block
        self.eval_dict = None

    def __iter__(self):
        yield from self.symbols.values()

    def __getitem__(self, symbolname: str) -> SymbolDefinition:
        return self.symbols[symbolname]

    def __contains__(self, symbolname: str) -> bool:
        return symbolname in self.symbols

    def lookup(self, dottedname: str) -> Tuple['SymbolTable', SymbolDefinition]:
        nameparts = dottedname.split('.')
        if len(nameparts) == 1:
            try:
                return self, self.symbols[nameparts[0]]
            except LookupError:
                raise SymbolError("undefined symbol '{:s}'".format(nameparts[0]))
        # start from toplevel namespace:
        scope = self
        while scope.parent:
            scope = scope.parent
        for namepart in nameparts[:-1]:
            try:
                scope = scope.symbols[namepart]
                assert scope.name == namepart
            except LookupError:
                raise SymbolError("undefined block '{:s}'".format(namepart))
        if isinstance(scope, SymbolTable):
            return scope.lookup(nameparts[-1])
        else:
            raise SymbolError("invalid block name '{:s}' in dotted name".format(namepart))

    def get_address(self, name: str) -> int:
        scope, symbol = self.lookup(name)
        if isinstance(symbol, ConstantDef):
            raise SymbolError("cannot take the address of a constant")
        if not symbol or not isinstance(symbol, VariableDef):
            raise SymbolError("no var or const defined by that name")
        if symbol.address is None:
            raise SymbolError("can only take address of memory mapped variables")
        return symbol.address

    def as_eval_dict(self) -> Dict[str, Any]:
        # return a dictionary suitable to be passed as locals or globals to eval()
        if self.eval_dict is None:
            d = {}
            for variable in self.iter_variables():
                d[variable.name] = variable.value
            for constant in self.iter_constants():
                d[constant.name] = constant.value
            for name, func in self.symbols.items():
                if inspect.isbuiltin(func):
                    d[name] = func
            self.eval_dict = d      # type: ignore
        return self.eval_dict

    def iter_variables(self) -> Iterable[VariableDef]:
        yield from sorted((v for v in self.symbols.values() if isinstance(v, VariableDef)))

    def iter_constants(self) -> Iterable[ConstantDef]:
        yield from sorted((v for v in self.symbols.values() if isinstance(v, ConstantDef)))

    def iter_subroutines(self) -> Iterable[SubroutineDef]:
        yield from sorted((v for v in self.symbols.values() if isinstance(v, SubroutineDef)))

    def iter_labels(self) -> Iterable[LabelDef]:
        yield from sorted((v for v in self.symbols.values() if isinstance(v, LabelDef)))

    def check_identifier_valid(self, name: str) -> None:
        if not name.isidentifier():
            raise SymbolError("invalid identifier")
        identifier = self.symbols.get(name, None)
        if identifier:
            if isinstance(identifier, SymbolDefinition):
                raise SymbolError("identifier was already defined at " + identifier.sourceref)
            raise SymbolError("identifier already defined as " + str(type(identifier)))

    def define_variable(self, name: str, sourcefile: str, sourceline: int, datatype: DataType, *,
                        address: int=None, length: int=0, value: Union[int, float, str]=0,
                        matrixsize: Tuple[int, int]=None, register: str=None) -> None:
        # this defines a new variable and also checks if the prefill value is allowed for the variable type.
        assert value is not None
        self.check_identifier_valid(name)
        range_error = check_value_in_range(datatype, register, length, value)
        if range_error:
            raise ValueError(range_error)
        if type(value) in (int, float):
            _, value = trunc_float_if_needed(sourcefile, sourceline, datatype, value)   # type: ignore
        allocate = address is None
        if datatype == DataType.BYTE:
            if allocate and self.name == "ZP":
                try:
                    address = zeropage.get_unused_byte()
                except LookupError:
                    raise SymbolError("too many global 8-bit variables in ZP")
            self.symbols[name] = VariableDef(self.name, name, sourcefile, sourceline, DataType.BYTE, allocate,
                                             value=value, length=1, address=address)
        elif datatype == DataType.WORD:
            if allocate and self.name == "ZP":
                try:
                    address = zeropage.get_unused_word()
                except LookupError:
                    raise SymbolError("too many global 16-bit variables in ZP")
            self.symbols[name] = VariableDef(self.name, name, sourcefile, sourceline, DataType.WORD, allocate,
                                             value=value, length=1, address=address)
        elif datatype == DataType.FLOAT:
            if allocate and self.name == "ZP":
                raise SymbolError("floats cannot be stored in the ZP")
            self.symbols[name] = VariableDef(self.name, name, sourcefile, sourceline, DataType.FLOAT, allocate,
                                             value=value, length=1, address=address)
        elif datatype == DataType.BYTEARRAY:
            self.symbols[name] = VariableDef(self.name, name, sourcefile, sourceline, DataType.BYTEARRAY, allocate,
                                             value=value, length=length, address=address)
        elif datatype == DataType.WORDARRAY:
            self.symbols[name] = VariableDef(self.name, name, sourcefile, sourceline, DataType.WORDARRAY, allocate,
                                             value=value, length=length, address=address)
        elif datatype in (DataType.STRING, DataType.STRING_P, DataType.STRING_S, DataType.STRING_PS):
            self.symbols[name] = VariableDef(self.name, name, sourcefile, sourceline, datatype, True,
                                             value=value, length=len(value))     # type: ignore
        elif datatype == DataType.MATRIX:
            length = matrixsize[0] * matrixsize[1]
            self.symbols[name] = VariableDef(self.name, name, sourcefile, sourceline, DataType.MATRIX, allocate,
                                             value=value, length=length, address=address, matrixsize=matrixsize)
        else:
            raise ValueError("unknown type " + str(datatype))
        self.eval_dict = None

    def define_sub(self, name: str, sourcefile: str, sourceline: int,
                   parameters: Sequence[Tuple[str, str]], returnvalues: Set[str], address: Optional[int]) -> None:
        self.check_identifier_valid(name)
        self.symbols[name] = SubroutineDef(self.name, name, sourcefile, sourceline, parameters, returnvalues, address)

    def define_label(self, name: str, sourcefile: str, sourceline: int) -> None:
        self.check_identifier_valid(name)
        self.symbols[name] = LabelDef(self.name, name, sourcefile, sourceline, False)

    def define_scope(self, scope: 'SymbolTable') -> None:
        self.check_identifier_valid(scope.name)
        self.symbols[scope.name] = scope

    def define_constant(self, name: str, sourcefile: str, sourceline: int, datatype: DataType, *,
                        length: int=0, value: Union[int, float, str]=0) -> None:
        # this defines a new constant and also checks if the value is allowed for the data type.
        assert value is not None
        self.check_identifier_valid(name)
        if type(value) in (int, float):
            _, value = trunc_float_if_needed(sourcefile, sourceline, datatype, value)   # type: ignore
        range_error = check_value_in_range(datatype, "", length, value)
        if range_error:
            raise ValueError(range_error)
        if datatype in (DataType.BYTE, DataType.WORD, DataType.FLOAT):
            self.symbols[name] = ConstantDef(self.name, name, sourcefile, sourceline, datatype, value=value, length=length or 1)
        elif datatype in STRING_DATATYPES:
            strlen = len(value)  # type: ignore
            self.symbols[name] = ConstantDef(self.name, name, sourcefile, sourceline, datatype, value=value, length=strlen)
        else:
            raise ValueError("invalid data type for constant: " + str(datatype))
        self.eval_dict = None


def trunc_float_if_needed(sourcefile: str, linenum: int, datatype: DataType,
                          value: Union[int, float]) -> Tuple[bool, Union[int, float]]:
    if type(value) not in (int, float):
        raise TypeError("can only truncate numbers")
    if datatype == DataType.FLOAT or type(value) is int or type(value) is str:
        return False, value
    frac = math.modf(value)     # type: ignore
    if frac == 0:
        return False, value
    if datatype in (DataType.BYTE, DataType.WORD, DataType.MATRIX):
        print("warning: {:s}:{:d}: Float value truncated.".format(sourcefile, linenum))
        return True, int(value)
    elif datatype == DataType.FLOAT:
        return False, value
    else:
        raise TypeError("invalid datatype passed")


def check_value_in_range(datatype: DataType, register: str, length: int, value: Union[int, float, str]) -> Optional[str]:
    if register:
        if register in REGISTER_BYTES:
            if value < 0 or value > 0xff:  # type: ignore
                return "value out of range, must be (unsigned) byte for a single register"
        elif register in REGISTER_WORDS:
            if value is None and datatype in (DataType.BYTE, DataType.WORD):
                return None
            if value < 0 or value > 0xffff:  # type: ignore
                return "value out of range, must be (unsigned) word for 2 combined registers"
        else:
            return "strange register..."
    elif datatype in (DataType.BYTE, DataType.BYTEARRAY, DataType.MATRIX):
        if value is None and datatype == DataType.BYTE:
            return None
        if value < 0 or value > 0xff:       # type: ignore
            return "value out of range, must be (unsigned) byte"
    elif datatype in (DataType.WORD, DataType.WORDARRAY):
        if value is None and datatype in (DataType.BYTE, DataType.WORD):
            return None
        if value < 0 or value > 0xffff:     # type: ignore
            return "value out of range, must be (unsigned) word"
    elif datatype in STRING_DATATYPES:
        if type(value) is not str:
            return "value must be a string"
    elif datatype == DataType.FLOAT:
        if type(value) not in (int, float):
            return "value must be a number"
    else:
        raise SymbolError("missing value check for type", datatype, register, length, value)
    return None  # all ok !
