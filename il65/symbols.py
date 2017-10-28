import enum
from functools import total_ordering
from typing import Optional, Set, Union, Tuple, Dict, Iterable, Sequence


@total_ordering
class VariableType(enum.Enum):
    """The type of a variable"""
    BYTE = 1
    WORD = 2
    CONSTANT = 3
    REGISTER = 4
    CHARACTER = 5
    BYTEARRAY = 6
    WORDARRAY = 7
    MATRIX = 8
    STRING = 9
    STRING_P = 10
    STRING_S = 11
    STRING_PS = 12

    def assignable_from_value(self, value: int) -> bool:
        if self in (VariableType.BYTE, VariableType.REGISTER):
            return 0 <= value < 0x100
        if self == VariableType.WORD:
            return 0 <= value < 0x10000
        return False

    def __lt__(self, other):
        if self.__class__ == other.__class__:
            return self.value < other.value
        return NotImplemented


STRING_VARTYPES = {VariableType.STRING, VariableType.STRING_P, VariableType.STRING_S, VariableType.STRING_PS}


class SymbolError(Exception):
    pass


_identifier_seq_nr = 0


class Identifier:
    __slots__ = ("block", "name", "sourceref", "allocate", "seq_nr")

    def __init__(self, block: str, name: str, sourcefile: str, sourceline: int, allocate: bool) -> None:
        self.block = block
        self.name = name
        self.sourceref = "{:s}:{:d}".format(sourcefile, sourceline)
        self.allocate = allocate     # set to false if the variable is memory mapped instead of allocated
        global _identifier_seq_nr
        self.seq_nr = _identifier_seq_nr
        _identifier_seq_nr += 1

    def __lt__(self, other: 'Identifier') -> bool:
        if not isinstance(other, Identifier):
            return NotImplemented
        return (self.block, self.name, self.seq_nr) < (other.block, other.name, self.seq_nr)

    def __str__(self):
        return "<{:s} {:s}.{:s}>".format(self.__class__.__name__, self.block, self.name)


class LabelIdentifier(Identifier):
    pass


class VariableIdentifier(Identifier):
    def __init__(self, block: str, name: str, sourcefile: str, sourceline: int, vtype: VariableType, allocate: bool, *,
                 value: Union[int, str], length: int, address: Optional[int]=None,
                 register: str=None, matrixsize: Tuple[int, int]=None) -> None:
        super().__init__(block, name, sourcefile, sourceline, allocate)
        self.type = vtype
        self.address = address
        self.length = length
        self.value = value
        self.register = register
        self.matrixsize = matrixsize

    def __repr__(self):
        return "<Variable {:s}.{:s}, {:s}, addr {:s}, len {:s}, value {:s}>"\
            .format(self.block, self.name, self.type, str(self.address), str(self.length), str(self.value))

    def __lt__(self, other: 'Identifier') -> bool:
        if not isinstance(other, VariableIdentifier):
            return NotImplemented
        v1 = (str(self.value) or "", self.block, self.name or "", self.address or 0, self.seq_nr)
        v2 = (str(other.value) or "", other.block, other.name or "", other.address or 0, self.seq_nr)
        return v1 < v2


class SubroutineIdentifier(Identifier):
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
        self.symbols = {}       # type: Dict[str, Identifier]

    def __getitem__(self, symbolname: str) -> Identifier:
        return self.symbols[symbolname]

    def __contains__(self, symbolname: str) -> bool:
        return symbolname in self.symbols

    def get(self, symbolname: str, default: Identifier=None) -> Optional[Identifier]:
        return self.symbols.get(symbolname, default)

    def iter_variables(self) -> Iterable[VariableIdentifier]:
        # returns specific sort order to optimize init sequence
        yield from sorted((v for v in self.symbols.values() if isinstance(v, VariableIdentifier)))

    def iter_subroutines(self) -> Iterable[SubroutineIdentifier]:
        yield from sorted((v for v in self.symbols.values() if isinstance(v, SubroutineIdentifier)))

    def iter_labels(self) -> Iterable[LabelIdentifier]:
        yield from sorted((v for v in self.symbols.values() if isinstance(v, LabelIdentifier)))

    def check_identifier_valid(self, name: str) -> None:
        if not name.isidentifier():
            raise SymbolError("invalid identifier")
        identifier = self.symbols.get(name, None)
        if identifier:
            raise SymbolError("identifier was already defined at " + identifier.sourceref)

    def define_variable(self, block: str, name: str, sourcefile: str, sourceline: int, vtype: VariableType, *,
                        address: int=None, length: int=0, value: Union[int, str]=0,
                        matrixsize: Tuple[int, int]=None, register: str=None) -> None:
        self.check_identifier_valid(name)
        allocate = address is None
        if vtype == VariableType.BYTE:
            if allocate:
                try:
                    address = self.zeropage.get_unused_byte()
                except LookupError:
                    raise SymbolError("too many 8-bit variables in zp")  # @todo make var in other memory
            self.symbols[name] = VariableIdentifier(block, name, sourcefile, sourceline, VariableType.BYTE, allocate,
                                                    value=value, length=1, address=address)
        elif vtype == VariableType.WORD:
            if allocate:
                try:
                    address = self.zeropage.get_unused_word()
                except LookupError:
                    raise SymbolError("too many 16-bit variables in zp")  # @todo make var in other memory
            self.symbols[name] = VariableIdentifier(block, name, sourcefile, sourceline, VariableType.WORD, allocate,
                                                    value=value, length=1, address=address)
        elif vtype == VariableType.BYTEARRAY:
            self.symbols[name] = VariableIdentifier(block, name, sourcefile, sourceline, VariableType.BYTEARRAY, allocate,
                                                    value=value, length=length, address=address)
        elif vtype == VariableType.WORDARRAY:
            self.symbols[name] = VariableIdentifier(block, name, sourcefile, sourceline, VariableType.WORDARRAY, allocate,
                                                    value=value, length=length, address=address)
        elif vtype == VariableType.CONSTANT:
            self.symbols[name] = VariableIdentifier(block, name, sourcefile, sourceline, VariableType.CONSTANT, False,
                                                    value=value, length=0)
        elif vtype == VariableType.REGISTER:
            self.symbols[name] = VariableIdentifier(block, name, sourcefile, sourceline, VariableType.REGISTER, False,
                                                    value=0, length=1, register=register)
        elif vtype in (VariableType.STRING, VariableType.STRING_P, VariableType.STRING_S, VariableType.STRING_PS):
            self.symbols[name] = VariableIdentifier(block, name, sourcefile, sourceline, vtype, True,
                                                    value=value, length=len(value))     # type: ignore
        elif vtype == VariableType.MATRIX:
            length = matrixsize[0] * matrixsize[1]
            self.symbols[name] = VariableIdentifier(block, name, sourcefile, sourceline, VariableType.MATRIX, allocate,
                                                    value=value, length=length, address=address, matrixsize=matrixsize)
        else:
            raise ValueError("unknown type "+str(vtype))

    def define_sub(self, block: str, name: str, sourcefile: str, sourceline: int,
                   parameters: Sequence[Tuple[str, str]], returnvalues: Set[str], address: Optional[int]) -> None:
        self.check_identifier_valid(name)
        self.symbols[name] = SubroutineIdentifier(block, name, sourcefile, sourceline, parameters, returnvalues, address)

    def define_label(self, block: str, name: str, sourcefile: str, sourceline: int) -> None:
        self.check_identifier_valid(name)
        self.symbols[name] = LabelIdentifier(block, name, sourcefile, sourceline, False)
