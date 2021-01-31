


def load_csv_trace():
    import csv
    TRACE_REF={}
    with open('./etc/trace_config.csv') as f:
        trace_description=csv.reader(f)
        for ref in trace_description:
            try:
                if ref[0][0]=='#':
                    continue
            except IndexError:
                continue
            # Load
            # <category>,<hex location>,<Comment>
            TRACE_REF[int(ref[1],16)]=(ref[0].strip(), ref[2].strip())
    return TRACE_REF            
#symbol_lines = [line.rstrip() for line in open('../c64mem/c64mem_src.txt')]






def load_64disasm():
    """
    This function merge the original C64 disassemble with the trace extracted from
    All_About_Your_64 
    """
    TRACE_REF={}
    # Load curated list first
    keep_me_only=load_csv_trace()
    for xcross in ['./etc/c64disasm_cbm.txt', './etc/c64disasm_ms.txt']:
        with open(xcross) as f:
            disassembler_lines=[line.rstrip() for line in f]
            for line in disassembler_lines:
                # Exmaple lines:
                # .,FFC0 6C 1A 03 JMP ($031A)     OPEN   JMP (IOPEN)     ;OPEN LOGICAL FILE
                # .,E5C8 18       CLC             CLC                    ;GOOD RETURN
                if line.startswith('.,'):
                    hex_line=line[2:6]
                    mem_line=int(hex_line,16)
                    if mem_line in keep_me_only:
                        if ';' in line:
                            # Take the disassembled part only                        
                            disassebled=(line[16:32].strip())
                            comment=line.split(';')[1]
                        else:                            
                            disassebled=line[16:32].strip()
                            comment="??"            
                        category=keep_me_only[mem_line][0]
                        strict_comment=keep_me_only[mem_line][1]
                        TRACE_REF[mem_line]=(
                            category,
                            "{:14.14};{:70.70}".format(disassebled,strict_comment)
                        )
                else:
                    continue               
    return TRACE_REF

def load_aay64():
    """Parse AAy64 
    FFED: 4C 05 E5  JMP $E505     ; Get Screen Size
    """
    TRACE_REF={}
    # Load curated list first
    keep_me_only=load_csv_trace()
    with open('./etc/AAY64.TXT') as f:
        disassembler_lines=[line.rstrip() for line in f]
        for line in disassembler_lines:
            try:
                if line[4]==":" and ';' in line:
                    hex_line=line[0:4]
                    mem_line=int(hex_line,16)
                    # Kernal (RANGE Exxx-Fxxx is always wellcome )
                    if mem_line in keep_me_only:
                        category=keep_me_only[mem_line][0]
                        strict_comment=line
                    elif hex_line.startswith('E'):
                        category='?KERNAL'
                        strict_comment=line
                    else:
                        # skip the definition
                        continue
                    # Assign data
                    TRACE_REF[mem_line]=(
                        category,
                        "{:65.65}".format(strict_comment.strip())
                    )
            except IndexError:
                continue
    return TRACE_REF

if __name__ == "__main__":
    #print(str(load_csv_trace()))
    #print(str(load_64disasm()))
    trace=load_aay64()
    print('Trace objects:{}'.format(len(trace)))
    print(str(trace)[0:160])
