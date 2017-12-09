import math
import enum
from functools import total_ordering
from typing import Optional, Set, Union, Tuple, Dict, Iterable, Sequence


@total_ordering
class DataType(enum.Enum):
    """The possible data types of values"""
    BYTE = 1
    WORD = 2
    FLOAT = 3
    REGISTER = 4        # @todo this is not really a data type
    CHARACTER = 5
    BYTEARRAY = 6
    WORDARRAY = 7
    MATRIX = 8
    STRING = 9
    STRING_P = 10
    STRING_S = 11
    STRING_PS = 12
    # @todo the integers are all unsigned, also support signed byte, word, bytearray, wordarray.

    def assignable_from_value(self, value: Union[int, float]) -> bool:
        if self in (DataType.BYTE, DataType.REGISTER):
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


STRING_VARTYPES = {DataType.STRING, DataType.STRING_P, DataType.STRING_S, DataType.STRING_PS}


class SymbolError(Exception):
    pass


_identifier_seq_nr = 0


class SymbolDefinition:
    __slots__ = ("block", "name", "sourceref", "allocate", "seq_nr")

    def __init__(self, block: str, name: str, sourcefile: str, sourceline: int, allocate: bool) -> None:
        self.block = block
        self.name = name
        self.sourceref = "{:s}:{:d}".format(sourcefile, sourceline)
        self.allocate = allocate     # set to false if the variable is memory mapped (or a constant) instead of allocated
        global _identifier_seq_nr
        self.seq_nr = _identifier_seq_nr
        _identifier_seq_nr += 1

    def __lt__(self, other: 'SymbolDefinition') -> bool:
        if not isinstance(other, SymbolDefinition):
            return NotImplemented
        return (self.block, self.name, self.seq_nr) < (other.block, other.name, self.seq_nr)

    def __str__(self):
        return "<{:s} {:s}.{:s}>".format(self.__class__.__name__, self.block, self.name)


class LabelDef(SymbolDefinition):
    pass


class VariableDef(SymbolDefinition):
    def __init__(self, block: str, name: str, sourcefile: str, sourceline: int, datatype: DataType, allocate: bool, *,
                 value: Union[int, float, str], length: int, address: Optional[int]=None,
                 register: str=None, matrixsize: Tuple[int, int]=None) -> None:
        super().__init__(block, name, sourcefile, sourceline, allocate)
        self.type = datatype
        self.address = address
        self.length = length
        self.value = value
        self.register = register
        self.matrixsize = matrixsize

    def __repr__(self):
        return "<Variable {:s}.{:s}, {:s}, addr {:s}, len {:s}, value {:s}>"\
            .format(self.block, self.name, self.type, str(self.address), str(self.length), str(self.value))

    def __lt__(self, other: 'SymbolDefinition') -> bool:
        if not isinstance(other, VariableDef):
            return NotImplemented
        v1 = (str(self.value) or "", self.block, self.name or "", self.address or 0, self.seq_nr)
        v2 = (str(other.value) or "", other.block, other.name or "", other.address or 0, self.seq_nr)
        return v1 < v2


class ConstantDef(SymbolDefinition):
    def __init__(self, block: str, name: str, sourcefile: str, sourceline: int, datatype: DataType, *,
                 value: Union[int, float, str], length: int, register: str=None) -> None:
        super().__init__(block, name, sourcefile, sourceline, False)
        self.type = datatype
        self.length = length
        self.value = value
        self.register = register

    def __repr__(self):
        return "<Constant {:s}.{:s}, {:s}, len {:s}, value {:s}>"\
            .format(self.block, self.name, self.type, str(self.length), str(self.value))

    def __lt__(self, other: 'SymbolDefinition') -> bool:
        if not isinstance(other, ConstantDef):
            return NotImplemented
        v1 = (str(self.value) or "", self.block, self.name or "", self.seq_nr)
        v2 = (str(other.value) or "", other.block, other.name or "", self.seq_nr)
        return v1 < v2


class SubroutineDef(SymbolDefinition):
    def __init__(self, block: str, name: str, sourcefile: str, sourceline: int,
                 parameters: Sequence[Tuple[str, str]], returnvalues: Set[str], address: Optional[int]=None) -> None:
        super().__init__(block, name, sourcefile, sourceline, False)
        self.address = address
        self.parameters = parameters
        self.input_registers = set()        # type: Set[str]
        self.return_registers = set()       # type: Set[str]
        self.clobbered_registers = set()    # type: Set[str]
        for _, param in parameters:
            if param in ("A", "X", "Y", "SC"):
                self.input_registers.add(param.lower())
            elif param in ("XY", "AX", "AY"):
                self.input_registers.add(param[0].lower())
                self.input_registers.add(param[1].lower())
            else:
                raise SymbolError("invalid parameter spec: " + param)
        for register in returnvalues:
            if register in ("A", "X", "Y", "AX", "AY", "XY"):
                self.return_registers.add(register.lower())
            elif len(register) == 2 and register[1] == '?' and register[0] in "AXY":
                self.clobbered_registers.add(register[0].lower())
            else:
                raise SymbolError("invalid return value spec: " + register)


class Zeropage:
    SCRATCH_B1 = 0x02
    SCRATCH_B2 = 0x03

    def __init__(self, clobber_zp: bool = False) -> None:
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


class SymbolTable:
    def __init__(self, zeropage: Zeropage) -> None:
        self.zeropage = zeropage
        self.symbols = {}       # type: Dict[str, SymbolDefinition]

    def __getitem__(self, symbolname: str) -> SymbolDefinition:
        return self.symbols[symbolname]

    def __contains__(self, symbolname: str) -> bool:
        return symbolname in self.symbols

    def get(self, symbolname: str, default: SymbolDefinition=None) -> Optional[SymbolDefinition]:
        return self.symbols.get(symbolname, default)

    def iter_variables(self) -> Iterable[VariableDef]:
        # returns specific sort order to optimize init sequence
        yield from sorted((v for v in self.symbols.values() if isinstance(v, VariableDef)))

    def iter_subroutines(self) -> Iterable[SubroutineDef]:
        yield from sorted((v for v in self.symbols.values() if isinstance(v, SubroutineDef)))

    def iter_labels(self) -> Iterable[LabelDef]:
        yield from sorted((v for v in self.symbols.values() if isinstance(v, LabelDef)))

    def check_identifier_valid(self, name: str) -> None:
        if not name.isidentifier():
            raise SymbolError("invalid identifier")
        identifier = self.symbols.get(name, None)
        if identifier:
            raise SymbolError("identifier was already defined at " + identifier.sourceref)

    def check_value_in_range(self, datatype: DataType, register: str, length: int, value: Union[int, float, str]) -> None:
        if datatype in (DataType.BYTE, DataType.BYTEARRAY, DataType.MATRIX):
            if value < 0 or value > 0xff:       # type: ignore
                raise ValueError("value too large, must be (unsigned) byte")
        elif datatype in (DataType.WORD, DataType.WORDARRAY):
            if value < 0 or value > 0xffff:     # type: ignore
                raise ValueError("value too large, must be (unsigned) word")
        elif datatype in STRING_VARTYPES:
            if type(value) is not str:
                raise ValueError("value must be a string")
        elif datatype == DataType.FLOAT:
            if type(value) not in (int, float):
                raise ValueError("value must be a number")
        else:
            raise SymbolError("missing value check for type", datatype, register, length, value)

    def define_variable(self, block: str, name: str, sourcefile: str, sourceline: int, datatype: DataType, *,
                        address: int=None, length: int=0, value: Union[int, float, str]=0,
                        matrixsize: Tuple[int, int]=None, register: str=None) -> None:
        # this defines a new variable and also checks if the prefill value is allowed for the variable type.
        self.check_identifier_valid(name)
        self.check_value_in_range(datatype, register, length, value)
        value = self.warn_if_float_trunc(sourcefile, sourceline, datatype, value)
        allocate = address is None
        if datatype == DataType.BYTE:
            if allocate:
                try:
                    address = self.zeropage.get_unused_byte()       # @todo make allocating a global ZP variable explicit in the declaration
                except LookupError:
                    raise SymbolError("too many global 8-bit variables in zp")  # @todo make var in other memory
            self.symbols[name] = VariableDef(block, name, sourcefile, sourceline, DataType.BYTE, allocate,
                                             value=value, length=1, address=address)
        elif datatype == DataType.WORD:
            if allocate:
                try:
                    address = self.zeropage.get_unused_word()       # @todo make allocating a global ZP variable explicit in the declaration
                except LookupError:
                    raise SymbolError("too many global 16-bit variables in zp")  # @todo make var in other memory
            self.symbols[name] = VariableDef(block, name, sourcefile, sourceline, DataType.WORD, allocate,
                                             value=value, length=1, address=address)
        elif datatype == DataType.FLOAT:
            if allocate:
                print("WARNING: FLOATS: cannot allocate outside of zp yet")  # @todo make var in other memory
                address = 0x7f00   # XXX
            self.symbols[name] = VariableDef(block, name, sourcefile, sourceline, DataType.FLOAT, allocate,
                                             value=value, length=1, address=address)
        elif datatype == DataType.BYTEARRAY:
            self.symbols[name] = VariableDef(block, name, sourcefile, sourceline, DataType.BYTEARRAY, allocate,
                                             value=value, length=length, address=address)
        elif datatype == DataType.WORDARRAY:
            self.symbols[name] = VariableDef(block, name, sourcefile, sourceline, DataType.WORDARRAY, allocate,
                                             value=value, length=length, address=address)
        elif datatype == DataType.REGISTER:
            self.symbols[name] = VariableDef(block, name, sourcefile, sourceline, DataType.REGISTER, False,
                                             value=0, length=1, register=register)
        elif datatype in (DataType.STRING, DataType.STRING_P, DataType.STRING_S, DataType.STRING_PS):
            self.symbols[name] = VariableDef(block, name, sourcefile, sourceline, datatype, True,
                                             value=value, length=len(value))     # type: ignore
        elif datatype == DataType.MATRIX:
            length = matrixsize[0] * matrixsize[1]
            self.symbols[name] = VariableDef(block, name, sourcefile, sourceline, DataType.MATRIX, allocate,
                                             value=value, length=length, address=address, matrixsize=matrixsize)
        else:
            raise ValueError("unknown type " + str(datatype))

    def define_sub(self, block: str, name: str, sourcefile: str, sourceline: int,
                   parameters: Sequence[Tuple[str, str]], returnvalues: Set[str], address: Optional[int]) -> None:
        self.check_identifier_valid(name)
        self.symbols[name] = SubroutineDef(block, name, sourcefile, sourceline, parameters, returnvalues, address)

    def define_label(self, block: str, name: str, sourcefile: str, sourceline: int) -> None:
        self.check_identifier_valid(name)
        self.symbols[name] = LabelDef(block, name, sourcefile, sourceline, False)

    def define_constant(self, block: str, name: str, sourcefile: str, sourceline: int, datatype: DataType, *,
                        length: int=0, value: Union[int, float, str]=0, register: str=None) -> None:
        # this defines a new constant and also checks if the value is allowed for the data type.
        self.check_identifier_valid(name)
        self.check_value_in_range(datatype, register, length, value)
        value = self.warn_if_float_trunc(sourcefile, sourceline, datatype, value)
        if datatype in (DataType.BYTE, DataType.WORD, DataType.FLOAT, DataType.CHARACTER, DataType.REGISTER):
            self.symbols[name] = ConstantDef(block, name, sourcefile, sourceline, datatype,
                                             value=value, length=length or 1, register=register)
        elif datatype in STRING_VARTYPES:
            self.symbols[name] = ConstantDef(block, name, sourcefile, sourceline, datatype,
                                             value=value, length=len(value))        # type: ignore
        else:
            raise ValueError("invalid data type for constant: " + str(datatype))

    def warn_if_float_trunc(self, sourcefile: str, linenum: int, datatype: DataType,
                            value: Union[int, float, str]) -> Union[int, float, str]:
        if datatype == DataType.FLOAT or type(value) is int or type(value) is str:
            return value
        frac = math.modf(value)     # type: ignore
        if frac == 0:
            return value
        if datatype in (DataType.REGISTER, DataType.BYTE):
            print("Warning: {:s}:{:d}: Float value truncated (byte).".format(sourcefile, linenum))
            return int(value)
        elif datatype == DataType.WORD:
            print("Warning: {:s}:{:d}: Float value truncated (word).".format(sourcefile, linenum))
            return int(value)
        elif datatype == DataType.FLOAT:
            return value
        else:
            raise TypeError("invalid datatype passed")
