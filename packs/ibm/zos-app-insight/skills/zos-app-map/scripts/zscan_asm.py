#!/usr/bin/env python3
"""zscan_asm: HLASM (z/OS Assembler) programs for the zos-app-insight map.

A library module next to zscan.py; zscan imports it for Assembler members. It has no
CLI and no import-time side effects:

  LANGUAGE = "asm"
  classify(path, text) -> "program" | "include" | "skip"
  scan_program(path, include_dirs, root=None) -> dict

`scan_program` returns one program record in the app-map contract version 1 shape
(references/map-format.md) with `language: "asm"`. Every 1.0 key is there; keys the
language has no use for are empty lists or null. The mapping:

  id           the first CSECT, RSECT, START or ENTRY name, else the member name
  copybooks    COPY members (and EXEC SQL INCLUDE members) as `{name, library: null, ...}`;
               macro definitions found as members of the include folders as
               `{name, library: "MACRO", resolved, line (first call), ...}`
  files        DCB and ACB with DDNAME (kind "DCB" or "ACB"); io from OPEN, CLOSE, GET, PUT,
               PUTX, READ, WRITE, CHECK, POINT, NOTE and the VSAM request macros (RPL=)
  data_items   DS and DC: a DSECT is a level-1 item and its fields are its children;
               a `DS 0CLn` group holds the fields that follow it within n bytes;
               the duplication factor is `occurs`; `ORG label` gives `redefines`
  paragraphs   labels on instructions and executable macros, `label DS 0H` and
               `label EQU *` outside DSECTs; `sections` are the control sections
  performs     BAL, BAS, BRAS, BRASL, JAS, JASL to a label of the module
  calls        CALL, LINK, XCTL, LOAD, ATTACH (EP= name: static; EPLOC=, DE= or a register:
               dynamic) and V-type address constants
  gotos        the branch family to a label
  sql, cics    EXEC SQL and EXEC CICS
  conditions   always empty: compare-and-branch pairs are statements, not business rules
  statements   every statement of open code except listing controls; `verb` is the
               operation code (`EXEC SQL`, `EXEC CICS` for those)

Keys added for Assembler (readers must not fail when they are missing):

  program     language "asm"; partial (a COPY member not found);
              macros [{name, found, definition (path or null), definition_line, inline,
              system (a known IBM macro), count, line (first call), copybook?}];
              macro_definitions [{name, start_line, end_line, copybook?}] (MACRO ... MEND
              in the member or its COPY members); equates [{name, value, line,
              control_section, file, copybook?}]; usings [{verb USING|DROP, line, operands,
              paragraph, label, copybook?}] (recorded, not interpreted); entries [{name,
              line}]; externals [{name, line, kind EXTRN|WXTRN}]; loops [{line, file, opcode,
              top, start_line, end_line, type, confidence, copybook?}]
  in_loop     {via, kind, file, confidence}: kind "branch" (via is the line of the branch
              that closes the loop) or "do" (via is the DO line); confidence "high" (BCT,
              BXH, BXLE families, DO WHILE/UNTIL/FROM/INF), "medium" (a conditional branch
              back to an earlier label, or BCTR to an address an LA loaded), "low" (an
              unconditional branch back with a conditional exit past it). A range holding
              a return (BR, PR, BSM, RETURN...) is not taken for a loop. Statements a BAL
              reaches from inside a loop are in that loop, the nearest one winning.
  loops.type  count, index, conditional, unconditional or do
  statements  label, kind (instruction, macro, data, directive, conditional, exec)
  performs    opcode, register (the link register)
  gotos       opcode, conditional, backward (null when the target is not a label here);
              depending_on is the index register of a computed branch (B TABLE(R15))
  calls       kind (CALL, LINK, LINKX, XCTL, XCTLX, LOAD, ATTACH, ATTACHX or V-con);
              candidates on dynamic calls (DC C'..' values and MVC =C'..' literals of an
              EPLOC= field)
  data_items  type, length (one value), dup (int, or the expression as written), nominal,
              size (bytes; a DS 0CLn group spans n), offset (from the start of the control
              section when known, else null), definition (the operand field), op (DS, DC,
              DSECT or a macro name for a list form), control_section; section is the
              control-section kind (CSECT, DSECT, ...); usage names the type in words
  files       options (the keyword operands as written), rpls (RPL names of an ACB)
  sections    kind (CSECT, RSECT, DSECT, START, COM, LOCTR), amode and rmode when given

The reader is heuristic, not an assembler. Macros are not expanded and conditional
assembly is not evaluated: statements on every path of AIF and AGO are mapped and a
warning says so. Source text is data: nothing read from it is executed or followed.
Python standard library only; Python 3.9 or later.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

LANGUAGE = "asm"
MAX_COPY_DEPTH = 12
BCTR_LOOKBACK = 40  # statements searched back for the LA that loads a BCTR target

_ZSCAN = None


def _z():
    """zscan, imported on first use: by name when its folder is on sys.path, else by file."""
    global _ZSCAN
    if _ZSCAN is None:
        try:
            import zscan as module  # noqa: F401 - the scripts folder is on sys.path when zscan runs
        except ImportError:
            spec = importlib.util.spec_from_file_location("zscan", Path(__file__).resolve().with_name("zscan.py"))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        _ZSCAN = module
    return _ZSCAN


# --------------------------------------------------------------------------- operation codes
def _words(text: str) -> Set[str]:
    return set(text.split())


# Assembler instructions (not machine instructions, not macros).
DIRECTIVES = _words("""
ACONTROL ADATA AINSERT ALIAS AMODE CATTR CEJECT CNOP COM COPY CSECT DROP DSECT EJECT END ENTRY
EQU EXITCTL EXTRN ICTL ISEQ LOCTR LTORG MACRO MEND OPSYN ORG POP PRINT PROCESS PUNCH PUSH REPRO
RMODE RSECT SPACE START TITLE USING WXTRN XATTR
""")
DATA_OPS = _words("DS DC DXD CXD CCW CCW0 CCW1")
CONDITIONAL = _words("""
ACTR AEJECT AGO AGOB AIF AIFB ANOP AREAD ASPACE GBLA GBLB GBLC LCLA LCLB LCLC MEXIT MHELP MNOTE
SETA SETAF SETB SETC SETCF
""")
LISTING = _words("CEJECT EJECT PRINT SPACE TITLE ASPACE AEJECT")
SECTION_OPS = _words("CSECT RSECT DSECT START COM LOCTR")
NO_OPERAND = _words("""
CSECT RSECT DSECT COM LOCTR LTORG ANOP MEND MEXIT MACRO EJECT PR UPT SAM24 SAM31 SAM64 TAM CSCH
HSCH RSCH XSCH IPK PTLB SCHM TEND
""")

# z/Architecture machine instructions an application program is likely to hold, plus the
# extended branch mnemonics. An operation code not here, not an assembler instruction and
# not a known macro is read as a macro call.
MACHINE = _words("""
A AFI AG AGF AGFI AGFR AGH AGHI AGHIK AGR AGRK AGSI AH AHHHR AHHLR AHI AHIK AHY AIH AL ALC ALCG
ALCGR ALCR ALFI ALG ALGF ALGFI ALGFR ALGHSIK ALGR ALGRK ALGSI ALHHHR ALHHLR ALHSIK ALR ALRK ALSI
ALSIH ALSIHN ALY AR ARK ASI AY
BAL BALR BAS BASR BASSM BC BCR BCT BCTG BCTGR BCTR BIC BPP BPRP BRAS BRASL BRC BRCL BRCT BRCTG
BRCTH BRXH BRXHG BRXLE BRXLG BSM BXH BXHG BXLE BXLEG
C CDS CDSG CDSY CFC CFI CG CGF CGFI CGFR CGFRL CGH CGHI CGHRL CGHSI CGR CGRL CH CHF CHHR CHHSI CHI
CHLR CHRL CHSI CHY CIH CKSM CL CLC CLCL CLCLE CLCLU CLFHSI CLFI CLG CLGF CLGFI CLGFR CLGFRL
CLGHRL CLGHSI CLGR CLGRL CLHF CLHHR CLHHSI CLHLR CLHRL CLI CLIH CLIY CLM CLMH CLMY CLR CLRL CLST
CLY CMPSC CR CRL CS CSG CSST CSY CU12 CU14 CU21 CU24 CU41 CU42 CUSE CUTFU CUUTF CVB CVBG CVBY CVD
CVDG CVDY CY
D DL DLG DLGR DLR DR DSG DSGF DSGFR DSGR
EAR ECAG ECTG ED EDMK EPSW ETND EX EXRL FLOGR
IC ICM ICMH ICMY ICY IIHF IIHH IIHL IILF IILH IILL IPM
KIMD KLMD KM KMAC KMC KMCTR KMF KMO
L LA LAA LAAG LAAL LAALG LAE LAEY LAM LAMY LAN LANG LAO LAOG LARL LAT LAX LAXG LAY LB LBH LBR
LCGFR LCGR LCR LG LGAT LGB LGBR LGF LGFI LGFR LGFRL LGG LGH LGHI LGHR LGHRL LGR LGRL LGSC LH LHH
LHI LHR LHRL LHY LLC LLCH LLCR LLGC LLGCR LLGF LLGFAT LLGFR LLGFRL LLGFSG LLGH LLGHR LLGHRL LLGT
LLGTAT LLGTR LLH LLHH LLHR LLHRL LLIHF LLIHH LLIHL LLILF LLILH LLILL LLZRGF LM LMD LMG LMH LMY
LNGFR LNGR LNR LOC LOCFH LOCFHR LOCG LOCGHI LOCGR LOCHHI LOCHI LOCR LPD LPDG LPGFR LPGR LPQ LPR LR
LRL LRV LRVG LRVGR LRVH LRVR LT LTG LTGF LTGFR LTGR LTR LY LZRF LZRG
M MC MFY MG MGH MGRK MH MHI MHY ML MLG MLGR MLR MR MS MSC MSFI MSG MSGC MSGF MSGFI MSGFR MSGR
MSGRKC MSR MSRKC MSY MVC MVCDK MVCIN MVCK MVCL MVCLE MVCLU MVCOS MVCP MVCS MVCSK MVGHI MVHHI MVHI
MVI MVIY MVN MVO MVST MVZ
N NC NCGRK NCRK NG NGR NGRK NI NIAI NIHF NIHH NIHL NILF NILH NILL NIY NNGRK NNRK NOGRK NORK NR
NRK NTSTG NXGRK NXRK NY
O OC OCGRK OCRK OG OGR OGRK OI OIHF OIHH OIHL OILF OILH OILL OIY OR ORK OY
PACK PKA PKU PFD PFDRL PFPO PLO POPCNT PPA
RISBG RISBGN RISBHG RISBLG RLL RLLG RNSBG ROSBG RXSBG
S SAM24 SAM31 SAM64 SAR SG SGF SGFR SGH SGR SGRK SH SHHHR SHHLR SHY SL SLA SLAG SLAK SLB SLBG
SLBGR SLBR SLDA SLDL SLFI SLG SLGF SLGFI SLGFR SLGR SLGRK SLHHHR SLHHLR SLL SLLG SLLK SLR SLRK
SLY SR SRA SRAG SRAK SRDA SRDL SRK SRL SRLG SRLK SRST SRSTU ST STAM STAMY STC STCH STCK STCKE
STCKF STCM STCMH STCMY STCY STFH STFLE STG STGRL STGSC STH STHH STHRL STHY STM STMG STMH STMY
STOC STOCFH STOCG STPQ STRL STRV STRVG STRVH STY SVC SY
TABORT TAM TBEGIN TBEGINC TEND TM TMH TMHH TMHL TML TMLH TMLL TMY TP TR TRE TROO TROT TRT TRTE
TRTO TRTR TRTRE TRTT TS
UNPK UNPKA UNPKU UPT X XC XG XGR XGRK XI XIHF XILF XIY XR XRK XY ZAP
AP CP DP MP SP SRP
AD ADB ADBR ADR ADTR AE AEB AEBR AER AU AUR AW AWR AXBR AXR AXTR CD CDB CDBR CDFBR CDGBR CDR CDTR
CE CEB CEBR CEFBR CEGBR CER CFDBR CFEBR CGDBR CGEBR CPSDR CXBR CXR DD DDB DDBR DDR DDTR DE DEB DEBR
DER DXBR DXR EFPC FIDBR FIDR FIEBR FIER HDR HER LCDFR LCDR LCER LCXR LD LDE LDEB LDEBR LDER LDGR
LDR LDXBR LDXR LDY LE LEDBR LEDR LER LEXBR LEXR LEY LFPC LGDR LNDFR LNDR LNER LPDFR LPDR LPER LRDR
LRER LTDBR LTDR LTEBR LTER LTXBR LTXR LXDBR LXDR LXR LZDR LZER LZXR MAD MADB MADBR MADR MAE MAEB
MAEBR MAER MD MDB MDBR MDE MDEB MDEBR MDER MDR MDTR ME MEE MEEB MEEBR MEER MER MSDB MSDBR MXBR MXD
MXDB MXDBR MXDR MXR SD SDB SDBR SDR SDTR SE SEB SEBR SER SFPC SQD SQDB SQDBR SQDR SQE SQEB SQEBR
SQER SQXBR SQXR SRNM SRNMB STD STDY STE STEY STFPC SU SUR SW SWR SXBR SXR SXTR TCDB TCEB TCXB
BAKR BSA BSG CSCH CSP CSPG DIAG EPAR EPAIR EREG EREGG ESAR ESAIR ESEA ESTA IAC IDTE IPK IPTE ISKE
IVSK LASP LCTL LCTLG LPSW LPSWE LRA LRAG LRAY LURA LURAG MSCH MSTA MVPG PALB PC PGIN PGOUT PR PT
PTF PTFF PTI PTLB RCHP RP RRBE RRBM RSCH SAC SACF SAL SCHM SCK SCKC SCKPF SIE SIGP SPKA SPM SPT
SPX SSAIR SSAR SSCH SSKE SSM STAP STCKC STCPS STCRW STCTG STCTL STFL STIDP STNSM STOSM STPT STPX
STRAG STSCH STSI STURA STURG TAR TB TPI TPROT TRACE TRACG TRAP2 TRAP4 TSCH XSCH
B BR NOP NOPR J JNOP JC JLC JLU JLNOP JAS JASL JCT JCTG JCTH JXH JXHG JXLE JXLEG BRU BRUL
""")
COND_SUFFIX = ("H", "L", "E", "NH", "NL", "NE", "O", "P", "M", "Z", "NO", "NP", "NM", "NZ")
COMPARE_BRANCH = _words("CRJ CGRJ CIJ CGIJ CLRJ CLGRJ CLIJ CLGIJ")  # relative, label target
COMPARE_BRANCH_REG = _words("CRB CGRB CIB CGIB CLRB CLGRB CLIB CLGIB")  # target is an address
COMPARE_TRAP = _words("CRT CGRT CIT CGIT CLRT CLGRT CLFIT CLGIT CLT CLGT")
COND_LOAD_STORE = _words("LOC LOCG LOCR LOCGR STOC STOCG LOCHI LOCGHI LOCHHI LOCFH LOCFHR STOCFH SELR SELGR")
SUFFIXED = sorted(COMPARE_BRANCH | COMPARE_BRANCH_REG | COMPARE_TRAP | COND_LOAD_STORE)  # take a condition suffix

BAL_OPS = _words("BAL BAS BRAS BRASL JAS JASL")
COUNT_LOOP = _words("BCT BCTG BRCT BRCTG BRCTH JCT JCTG JCTH")
INDEX_LOOP = _words("BXH BXLE BXHG BXLEG BRXH BRXLE BRXHG BRXLG JXH JXLE JXHG JXLEG")
UNCOND = _words("B J BRU BRUL JLU")
NO_BRANCH = _words("NOP JNOP JLNOP NOPR")
MASK_BRANCH = _words("BC BRC BRCL JC JLC")
RETURN_OPS = _words("BR PR BSM RETURN DFHEIRET CEETERM")
FLOW_END = RETURN_OPS | _words("ABEND XCTL XCTLX")

# Known IBM macros: executable ones, ones that build control blocks or list forms (their
# label names storage), and mapping macros (DSECTs and equates only).
EXEC_MACROS = _words("""
ABEND ALESERV ATTACH ATTACHX BLDL BSP CALL CHAP CHECK CLOSE CNTRL CPOOL CSVQUERY DELETE DEQ DETACH
DOM DYNALLOC ENDREQ ENQ ERASE ESPIE ESTAE ESTAEX EXCP EXCPVR EXTRACT FEOV FIND FREEMAIN FREEPOOL
FREEBUF GENCB GET GETBUF GETMAIN GETPOOL IARV64 IDENTIFY IEANTCR IEANTDL IEANTRT ISGENQ LINK
LINKX LOAD MODCB MODESET NOTE OPEN POINT POST PUT PUTX RACHECK RACINIT RACROUTE READ RELSE RESERVE
RETURN SAVE SDUMP SDUMPX SETFRR SETRP SHOWCB SNAP SNAPX SPIE STAE STIMER STIMERM STORAGE STOW SYNADAF
SYNADRLS SYNCH SYNCHX TCBTOKEN TESTCB TIME TIMEUSED TRUNC TTIMER VERIFY WAIT WTL WTO WTOR WRITE
XCTL XCTLX CEEENTRY CEETERM DFHEIENT DFHEIRET TPUT TGET PUTLINE GETLINE STAX
IF ELSE ENDIF DO ENDDO DOEXIT ASMLEAVE ITERATE SELECT WHEN OTHRWISE ENDSEL CASENTRY CASE ENDCASE
STRTSRCH ORELSE ENDLOOP ENDSRCH EXITIF
""")
DATA_MACROS = _words("DCB DCBE ACB RPL EXLST NIB CEEPPA DFHEISTG DFHEIEND")
MAPPING_MACROS = _words("""
DCBD IHADCB IFGACB IFGRPL IFGEXLST CVT IHAPSA IHASDWA IHAFRRS IHAASCB IHAASXB IHAACEE IHAECB
IHAPVT IHACDE IHARB IKJTCB IHATCB IHASTCB IHAWQE IHAJSCB IEZJSCB IEFJFCBN IEFUCBOB IEZDEB IEFTIOT1
IEFZB4D0 IEFZB4D2 ICHSAFP CEECAA CEEDSA YREGS EQUREGS ASMDREG DSNDXAPL DSNDEXPL DSNXAPRV DFHAID
DFHBMSCA SYSSTATE IEABRC ASMMREL
""")
SYSTEM_MACROS = EXEC_MACROS | DATA_MACROS | MAPPING_MACROS
EQU_MACROS = _words("YREGS EQUREGS ASMDREG REGEQU")  # register equates only: no storage

IO_FIRST = _words("GET PUT PUTX POINT NOTE BSP CNTRL TRUNC RELSE FEOV ERASE ENDREQ VERIFY")
OPEN_MODES = _words("INPUT OUTPUT UPDAT EXTEND OUTIN INOUT RDBACK OUTINX")
CALL_MACROS = _words("CALL LINK LINKX XCTL XCTLX LOAD ATTACH ATTACHX")

ASM_EXT = (".mac", ".macro", ".asm", ".s390", ".hlasm", ".asmcopy", ".maclib", ".cpy", ".copy")
SYMBOL_START = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz@#$_")
SYMBOL_CHARS = SYMBOL_START | set("0123456789")

# DC/DS types: implicit length, alignment and a reader's name.
TYPE_INFO = {
    "C": (None, 1, "character"), "CA": (None, 1, "character (ASCII)"), "CE": (None, 1, "character (EBCDIC)"),
    "CU": (None, 2, "character (Unicode)"), "G": (None, 1, "graphic"), "X": (None, 1, "hexadecimal"),
    "B": (None, 1, "binary"), "P": (None, 1, "packed decimal"), "Z": (None, 1, "zoned decimal"),
    "F": (4, 4, "fullword integer"), "FD": (8, 8, "doubleword integer"), "H": (2, 2, "halfword integer"),
    "E": (4, 4, "short floating point"), "EH": (4, 4, "short floating point"),
    "EB": (4, 4, "short binary floating point"), "ED": (4, 4, "short decimal floating point"),
    "D": (8, 8, "long floating point"), "DH": (8, 8, "long floating point"),
    "DB": (8, 8, "long binary floating point"), "DD": (8, 8, "long decimal floating point"),
    "L": (16, 8, "extended floating point"), "LH": (16, 8, "extended floating point"),
    "LB": (16, 8, "extended binary floating point"), "LD": (16, 8, "extended decimal floating point"),
    "LQ": (16, 16, "extended floating point"),
    "A": (4, 4, "address"), "AD": (8, 8, "address"), "Y": (2, 2, "address"), "S": (2, 2, "base-displacement"),
    "V": (4, 4, "external address"), "VD": (8, 8, "external address"), "Q": (4, 4, "offset"),
    "QD": (8, 8, "offset"), "J": (4, 4, "length"), "JD": (8, 8, "length"), "R": (4, 4, "address"),
    "RD": (8, 8, "address"),
}
TYPE_EXT = {"C": "AEU", "E": "HBD", "D": "HBD", "L": "HBDQ", "A": "D", "F": "D", "V": "D", "Q": "D", "J": "D",
            "R": "D"}


# --------------------------------------------------------------------------- logical statements
class Stmt:
    """One logical statement: fields of the first line, operands joined from continuation lines."""

    __slots__ = ("label", "op", "operand", "line", "end_line", "src", "kind", "ops", "para", "sect", "loop", "idx")

    def __init__(self, label: Optional[str], op: str, operand: str, line: int, end_line: int):
        self.label = label
        self.op = op
        self.operand = operand
        self.line = line
        self.end_line = end_line
        self.src = 0
        self.kind = ""
        self.ops: List[str] = []
        self.para: Optional[str] = None
        self.sect: Optional[int] = None
        self.loop: Optional[dict] = None
        self.idx = 0

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Stmt({self.label!r},{self.op!r},{self.operand!r},{self.line})"


class _Operand:
    """Collects an operand field: it ends at a blank outside quotes (and parentheses for SETx/AIF)."""

    def __init__(self, paren_blanks: bool):
        self.buf: List[str] = []
        self.quote = False
        self.pending = False  # a quote closed the string at the end of a line: maybe the first of ''
        self.depth = 0
        self.paren_blanks = paren_blanks

    def text(self) -> str:
        return "".join(self.buf)

    def _attribute(self, s: str, k: int) -> bool:
        prev = self.buf[-1] if self.buf else ""
        before = self.buf[-2] if len(self.buf) > 1 else ""
        return _is_attribute(prev, before, s[k + 1] if k + 1 < len(s) else "")

    def feed(self, s: str) -> Optional[int]:
        """Take the characters of s; the index of the blank that ends the field, or None."""
        k = 0
        while k < len(s):
            c = s[k]
            if self.pending:
                self.pending = False
                if c == "'":
                    self.buf.append(c)
                    k += 1
                    continue
                self.quote = False
            if self.quote:
                self.buf.append(c)
                if c == "'":
                    if k + 1 >= len(s):
                        self.pending = True
                    elif s[k + 1] == "'":
                        self.buf.append("'")
                        k += 2
                        continue
                    else:
                        self.quote = False
                k += 1
                continue
            if c == " ":
                if self.paren_blanks and self.depth > 0:
                    self.buf.append(c)
                    k += 1
                    continue
                return k
            if c == "'" and not self._attribute(s, k):
                self.quote = True
            elif c == "(":
                self.depth += 1
            elif c == ")":
                self.depth = max(0, self.depth - 1)
            self.buf.append(c)
            k += 1
        return None


def _is_symbol(text: Optional[str]) -> bool:
    return bool(text) and text[0] in SYMBOL_START and all(c in SYMBOL_CHARS for c in text)


def _is_attribute(prev: str, before: str, nxt: str) -> bool:
    """An apostrophe after L, D, T, K, N, I, S or O that starts L'X, D'X, T'&X...: an
    attribute reference, not the start of a string (D'1.5' and L'2' stay constants)."""
    return (prev != "" and prev.upper() in "LDTKNISO" and before not in SYMBOL_CHARS
            and (nxt in SYMBOL_START or nxt in "&*"))


def _continuation(raw: str, begin: int, cont: int) -> bool:
    return not raw[begin - 1:cont - 1].strip() and bool(raw[cont - 1:].strip())


def logical_statements(lines: Sequence[str], file: Optional[str] = None,
                       warnings: Optional[List[dict]] = None) -> List[Stmt]:
    """The statements of a member in order, macro definition bodies included.

    Columns: name from column 1, statement text to column 71, continuation indicator in
    column 72, continuation lines from column 16, sequence numbers (73-80) ignored; ICTL
    as the first statement changes them. Comment lines start with `*` or `.*`. Reading
    stops at END outside a macro definition.
    """
    warns = warnings if warnings is not None else []
    out: List[Stmt] = []
    begin, end, cont = 1, 71, 16
    n = len(lines)
    i = 0
    depth = 0
    while i < n:
        raw = lines[i].expandtabs(8)
        start = i + 1
        i += 1
        body = raw[begin - 1:end]
        continued = bool(raw[end:end + 1].strip())
        if not body.strip() or body.startswith("*") or body.startswith(".*"):
            while continued and i < n and _continuation(lines[i].expandtabs(8), begin, cont):
                continued = bool(lines[i].expandtabs(8)[end:end + 1].strip())
                i += 1
            continue
        k = 0
        label = None
        if body[0] != " ":
            while k < len(body) and body[k] != " ":
                k += 1
            label = body[:k]
        while k < len(body) and body[k] == " ":
            k += 1
        if k >= len(body):
            while continued and i < n and _continuation(lines[i].expandtabs(8), begin, cont):
                continued = bool(lines[i].expandtabs(8)[end:end + 1].strip())
                i += 1
            continue
        m = k
        while m < len(body) and body[m] != " ":
            m += 1
        op = body[k:m].upper()
        while m < len(body) and body[m] == " ":
            m += 1
        rest = body[m:]
        raw_mode = op == "EXEC"
        scanner = _Operand(paren_blanks=op in CONDITIONAL or (label or "").startswith("&"))
        parts: List[str] = []
        if raw_mode:
            parts.append(rest)
            state = "direct"
        elif op in NO_OPERAND:
            state = "remarks"
        else:
            stop = scanner.feed(rest)
            if stop is None:
                state = "direct" if rest else "fresh"
            else:
                state = "fresh" if scanner.text().endswith(",") or not scanner.text() else "remarks"
        last = start
        while continued and i < n:
            nraw = lines[i].expandtabs(8)
            if not _continuation(nraw, begin, cont):
                if file is not None:
                    warns.append({"file": file, "line": i + 1,
                                  "message": f"column {end + 1} of line {last} is not blank but line {i + 1} is not "
                                             f"a continuation line; read as a new statement"})
                break
            i += 1
            last = i
            chunk = nraw[cont - 1:end]
            continued = bool(nraw[end:end + 1].strip())
            if raw_mode:
                parts.append(chunk)
                continue
            if state == "remarks" or not chunk.strip():
                continue
            stop = scanner.feed(chunk if state == "direct" else chunk.lstrip())
            if stop is None:
                state = "direct"
            else:
                state = "fresh" if scanner.text().endswith(",") else "remarks"
        operand = " ".join("".join(parts).split()) if raw_mode else scanner.text()
        if op == "ICTL" and not out:
            nums = [x for x in operand.split(",") if x.strip().isdigit()]
            if nums:
                begin = int(nums[0])
                end = int(nums[1]) if len(nums) > 1 else 71
                cont = int(nums[2]) if len(nums) > 2 else 16
            continue
        st = Stmt(label, op, operand, start, last)
        out.append(st)
        if op == "REPRO":
            i += 1  # the next line is data for the object deck
        if op == "MACRO":
            depth += 1
        elif op == "MEND":
            depth = max(0, depth - 1)
        elif op == "END" and depth == 0:
            tail = [k2 for k2 in range(i, n)
                    if lines[k2].expandtabs(8)[begin - 1:end].strip()
                    and not lines[k2].expandtabs(8)[begin - 1:end].startswith(("*", ".*"))]
            if tail and file is not None:
                warns.append({"file": file, "line": tail[0] + 1, "message": "text after END is not analysed"})
            break
    return out


def open_code(stmts: Sequence[Stmt], file: Optional[str] = None,
              warnings: Optional[List[dict]] = None) -> Tuple[List[Stmt], List[dict]]:
    """Statements outside MACRO ... MEND, and the macro definitions {name, start_line, end_line}."""
    warns = warnings if warnings is not None else []
    out: List[Stmt] = []
    defs: List[dict] = []
    k = 0
    while k < len(stmts):
        st = stmts[k]
        if st.op != "MACRO":
            if st.op == "MEND" and file is not None:
                warns.append({"file": file, "line": st.line, "message": "MEND without MACRO; skipped"})
            elif st.op != "MEND":
                out.append(st)
            k += 1
            continue
        depth = 1
        proto = stmts[k + 1] if k + 1 < len(stmts) else None
        j = k + 1
        while j < len(stmts) and depth:
            if stmts[j].op == "MACRO":
                depth += 1
            elif stmts[j].op == "MEND":
                depth -= 1
            if depth:
                j += 1
        name = proto.op if proto is not None and proto.op != "MEND" else None
        if j >= len(stmts):
            if file is not None:
                warns.append({"file": file, "line": st.line, "message": "MACRO without MEND; the rest of the member is "
                                                                        "read as its definition"})
            defs.append({"name": name, "start_line": st.line, "end_line": stmts[-1].end_line})
            break
        defs.append({"name": name, "start_line": st.line, "end_line": stmts[j].end_line})
        k = j + 1
    return out, defs


def split_operands(text: str) -> List[str]:
    """Top-level operands: split at commas outside quotes and parentheses, as written."""
    out: List[str] = []
    cur: List[str] = []
    depth = 0
    quote = False
    k = 0
    while k < len(text):
        c = text[k]
        if quote:
            cur.append(c)
            if c == "'":
                if k + 1 < len(text) and text[k + 1] == "'":
                    cur.append("'")
                    k += 2
                    continue
                quote = False
            k += 1
            continue
        if c == "'":
            if not _is_attribute(cur[-1] if cur else "", cur[-2] if len(cur) > 1 else "",
                                 text[k + 1] if k + 1 < len(text) else ""):
                quote = True
        elif c == "(":
            depth += 1
        elif c == ")":
            depth = max(0, depth - 1)
        elif c == "," and depth == 0:
            out.append("".join(cur))
            cur = []
            k += 1
            continue
        cur.append(c)
        k += 1
    if cur or out:
        out.append("".join(cur))
    return out


def _inner(text: str) -> Optional[str]:
    """(A,B) -> A,B; None when text is not one parenthesised list."""
    t = text.strip()
    if len(t) >= 2 and t[0] == "(" and t[-1] == ")":
        depth = 0
        for k, c in enumerate(t):
            depth += {"(": 1, ")": -1}.get(c, 0)
            if depth == 0 and k < len(t) - 1:
                return None
        return t[1:-1]
    return None


def keywords(ops: Sequence[str]) -> Tuple[List[str], Dict[str, str]]:
    """Positional operands and KEY=value operands of a macro call, values as written."""
    pos: List[str] = []
    kw: Dict[str, str] = {}
    for o in ops:
        if "=" in o and not o.startswith("=") and _is_symbol(o.split("=", 1)[0]):
            key, value = o.split("=", 1)
            kw[key.upper()] = value
        else:
            pos.append(o)
    return pos, kw


# --------------------------------------------------------------------------- DS and DC operands
def _balanced(text: str, k: int) -> int:
    """Index after the parenthesis that closes the one at text[k]."""
    depth = 0
    quote = False
    first = k
    while k < len(text):
        c = text[k]
        if quote:
            if c == "'":
                quote = False
        elif c == "'":
            quote = not _is_attribute(text[k - 1] if k > first else "", text[k - 2] if k - 1 > first else "",
                                      text[k + 1] if k + 1 < len(text) else "")
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return k + 1
        k += 1
    return k


def _int(text: str) -> Optional[int]:
    t = text.strip()
    if t.startswith("(") and t.endswith(")"):
        t = t[1:-1].strip()
    return int(t) if t.isdigit() else None


def _split_values(nominal: str) -> List[str]:
    """Values of one nominal: 'A,B' or (A,B); a C or G constant is one value."""
    if not nominal:
        return []
    if nominal[0] == "(":
        inner = nominal[1:-1] if nominal.endswith(")") else nominal[1:]
        return split_operands(inner)
    body = nominal[1:-1] if len(nominal) > 1 and nominal.endswith("'") else nominal[1:]
    return [v for v in body.split(",")]


def _char_count(nominal: str) -> int:
    body = nominal[1:-1] if len(nominal) > 1 and nominal.endswith("'") else nominal[1:]
    return len(body.replace("''", "'").replace("&&", "&"))


def parse_constant(text: str) -> Optional[dict]:
    """One DS or DC operand: duplication, type, length and nominal value as written.

    Returns {dup, dup_text, type, pic, length, explicit, nominal, values, size, align} or None
    when the operand does not start like a constant. `length` is the length of one value
    (explicit or implicit), `size` the bytes of the whole operand; both are None when they
    rest on an expression or a form this reader does not compute.
    """
    t = text.strip()
    k = 0
    dup: Any = 1
    dup_text = None
    if k < len(t) and t[k].isdigit():
        j = k
        while j < len(t) and t[j].isdigit():
            j += 1
        dup = int(t[k:j])
        dup_text = t[k:j]
        k = j
    elif k < len(t) and t[k] == "(":
        j = _balanced(t, k)
        dup_text = t[k:j]
        dup = _int(dup_text)
        k = j
    if k >= len(t) or t[k].upper() not in "CGXBPZFHEDLAYSVQJR":
        return None
    typ = t[k].upper()
    k += 1
    if k < len(t) and t[k].upper() in TYPE_EXT.get(typ, "") and (typ + t[k].upper()) in TYPE_INFO:
        nxt = t[k + 1:k + 2]
        if not (t[k].upper() == "L" and nxt and (nxt.isdigit() or nxt in "(.")):
            typ += t[k].upper()
            k += 1
    pic_start = 0 if dup_text is None else len(dup_text)
    length: Optional[int] = None
    explicit = False
    if k < len(t) and t[k].upper() == "L":
        explicit = True
        k += 1
        if k < len(t) and t[k] == ".":
            k += 1
            j = k
            while j < len(t) and t[j].isdigit():
                j += 1
            k = j
            length = None
        elif k < len(t) and t[k] == "(":
            j = _balanced(t, k)
            length = _int(t[k:j])
            k = j
        else:
            j = k
            while j < len(t) and t[j].isdigit():
                j += 1
            length = int(t[k:j]) if j > k else None
            k = j
    for mod in ("S", "E"):
        if k < len(t) and t[k].upper() == mod and k + 1 < len(t) and (t[k + 1] in "(+-" or t[k + 1].isdigit()):
            k += 1
            if t[k] == "(":
                k = _balanced(t, k)
            else:
                if t[k] in "+-":
                    k += 1
                while k < len(t) and t[k].isdigit():
                    k += 1
    pic = t[pic_start:k]
    nominal = t[k:] if k < len(t) else ""
    if nominal and nominal[0] not in "'(":
        return None
    values = _split_values(nominal) if nominal else []
    info = TYPE_INFO.get(typ, (None, 1, None))
    implicit, align, _name = info
    if not explicit:
        if implicit is not None:
            length = implicit
        elif not nominal:
            length = 1 if typ != "CU" else 2
        elif typ in ("C", "CA", "CE"):
            length = _char_count(nominal)
        elif typ == "CU":
            length = 2 * _char_count(nominal)
        else:
            lengths = []
            for v in values:
                v = v.strip()
                if typ == "X":
                    lengths.append((len(v.replace(" ", "")) + 1) // 2)
                elif typ == "B":
                    lengths.append((len(v.replace(" ", "")) + 7) // 8)
                elif typ in ("P", "Z"):
                    digits = sum(ch.isdigit() for ch in v)
                    lengths.append((digits + 2) // 2 if typ == "P" else digits)
                else:
                    lengths.append(None)
            length = lengths[0] if lengths and all(x == lengths[0] for x in lengths) else None
    count = max(1, len(values)) if typ not in ("C", "CA", "CE", "CU", "G") else 1
    size = dup * length * count if isinstance(dup, int) and length is not None else None
    if typ == "G" and not explicit:
        length = size = None
    if dup == 0:
        size = 0
    return {"dup": dup, "dup_text": dup_text, "type": typ, "pic": pic, "length": length, "explicit": explicit,
            "nominal": nominal or None, "values": values, "size": size, "align": 1 if explicit else align}


# --------------------------------------------------------------------------- classify
def _machine(op: str) -> bool:
    if op in MACHINE:
        return True
    for base in SUFFIXED:
        if op.startswith(base) and op[len(base):] in COND_SUFFIX:
            return True
    return _branch_mnemonic(op) is not None


def _branch_mnemonic(op: str) -> Optional[Tuple[str, str]]:
    """Extended branch mnemonics: (form, condition); form rx, rr, rel or rell."""
    for prefix, form, suffix in (("BR", "rel", ""), ("BR", "rell", "L"), ("JL", "rell", ""), ("J", "rel", ""),
                                 ("B", "rx", ""), ("B", "rr", "R")):
        if op.startswith(prefix) and (not suffix or op.endswith(suffix)):
            cond = op[len(prefix):len(op) - len(suffix)] if suffix else op[len(prefix):]
            if cond in COND_SUFFIX:
                return form, cond
    return None


def _kind(st: Stmt, macro_names: Set[str]) -> str:
    op = st.op
    if op == "EXEC":
        return "exec"
    if op.startswith("&") or op in CONDITIONAL:
        return "conditional"
    if op in macro_names:
        return "macro"
    if op in DATA_OPS:
        return "data"
    if op in DIRECTIVES:
        return "directive"
    if _machine(op):
        return "instruction"
    return "macro"


def classify(path, text: str) -> str:
    """"program" (a CSECT, START or executable code), "include" (only DSECTs, EQUs, storage
    definitions or MACRO ... MEND definitions) or "skip" (no Assembler statement found)."""
    stmts, defs = open_code(logical_statements(text.splitlines()))
    if (not stmts and not defs) or _foreign(text, stmts):
        return "skip"
    names = {d["name"] for d in defs if d["name"]}
    has_end = False
    unknown_macro = False
    for st in stmts:
        kind = _kind(st, names)
        if st.op in ("CSECT", "RSECT", "START", "COM"):
            return "program"
        if kind == "instruction" or kind == "exec":
            return "program"
        if kind == "macro" and st.op in EXEC_MACROS and not _list_form(st.operand):
            return "program"
        if st.op == "END":
            has_end = True
        elif kind == "macro" and st.op not in MAPPING_MACROS and st.op not in DATA_MACROS:
            unknown_macro = True
    if has_end and unknown_macro:
        return "program"
    return "include"


def _foreign(text: str, stmts: Sequence[Stmt]) -> bool:
    """Plainly another language: JCL (//), a REXX or PL/I comment start (/*), COBOL
    division headers, or PL/I and REXX labels ending in a colon."""
    first = next((ln for ln in text.splitlines() if ln.strip()), "")
    if first.startswith("//") or first.lstrip().startswith("/*"):
        return True
    for st in stmts[:60]:
        if st.op in ("IDENTIFICATION", "ID") and st.operand.upper().startswith("DIVISION"):
            return True
        if st.op.startswith("PROGRAM-ID") or st.op.endswith(":") or (st.label or "").endswith(":"):
            return True
    return False


def _list_form(operand: str) -> bool:
    _, kw = keywords(split_operands(operand))
    mf = (kw.get("MF") or kw.get("SF") or "").upper().replace(" ", "")
    return mf == "L" or mf.startswith("(L")


# --------------------------------------------------------------------------- members
_INDEX_CACHE: Dict[Tuple[str, ...], Tuple[Dict[str, int], Dict[str, List[Path]]]] = {}
_MACRO_FILE_CACHE: Dict[str, Tuple[Tuple[int, int], Dict[str, int]]] = {}


def _stamp(path: str) -> int:
    try:
        return os.stat(path).st_mtime_ns
    except OSError:
        return -1  # missing: a folder created later changes the stamp


def _member_index(include_dirs: Sequence) -> Dict[str, List[Path]]:
    """Files by member name (stem, upper case) under the include folders, kept while no folder changes."""
    z = _z()
    key = tuple(os.path.realpath(str(d)) for d in include_dirs)
    hit = _INDEX_CACHE.get(key)
    if hit is not None and all(_stamp(d) == m for d, m in hit[0].items()):
        return hit[1]
    stamps: Dict[str, int] = {}
    index: Dict[str, List[Path]] = {}
    for folder in key:
        stamps[folder] = _stamp(folder)
        if not os.path.exists(folder):
            continue
        if os.path.isfile(folder):
            stamps[folder] = os.stat(folder).st_mtime_ns
            index.setdefault(Path(folder).stem.upper(), []).append(Path(folder))
            continue
        for dirpath, dirnames, filenames in os.walk(folder):
            dirnames[:] = sorted(d for d in dirnames if d not in z.SKIP_DIRS and not d.startswith("."))
            stamps[dirpath] = os.stat(dirpath).st_mtime_ns
            for name in sorted(filenames):
                p = Path(dirpath) / name
                if name.startswith(".") or os.path.islink(p):
                    continue
                index.setdefault(p.stem.upper(), []).append(p)
    _INDEX_CACHE[key] = (stamps, index)
    return index


def _ranked(found: List[Path], near: Path, exclude: Path) -> List[Path]:
    z = _z()
    here = os.path.realpath(near.parent).split(os.sep)
    skip = os.path.realpath(exclude)

    def score(item: Tuple[int, Path]):
        order, path = item
        ext = path.suffix.lower()
        ext_rank = 0 if ext in ASM_EXT else (1 if ext in z.UNKNOWN_EXT else 2)
        parts = os.path.realpath(path.parent).split(os.sep)
        common = 0
        for a, b in zip(here, parts):
            if a != b:
                break
            common += 1
        return ext_rank, -common, order

    usable = [(k, p) for k, p in enumerate(found) if os.path.realpath(p) != skip]
    return [p for _, p in sorted(usable, key=score)]


def _macros_in_file(path: Path) -> Dict[str, int]:
    """The macros a member defines: name -> line of its MACRO statement."""
    z = _z()
    real = os.path.realpath(path)
    try:
        st = os.stat(real)
    except OSError:
        return {}
    stamp = (st.st_mtime_ns, st.st_size)
    hit = _MACRO_FILE_CACHE.get(real)
    if hit is not None and hit[0] == stamp:
        return hit[1]
    try:
        text = z.read_text(Path(real))
    except OSError:
        return {}
    _, defs = open_code(logical_statements(text.splitlines()))
    names: Dict[str, int] = {}
    for d in defs:
        if d["name"]:
            names.setdefault(d["name"], d["start_line"])
    _MACRO_FILE_CACHE[real] = (stamp, names)
    return names


# --------------------------------------------------------------------------- branch targets
def _target(operand: str) -> Tuple[Optional[str], Optional[str], bool]:
    """(label, index register, register based) of a branch address as written.

    `*+8` and other location-counter or literal addresses give (None, None, False).
    """
    o = operand.strip()
    if not o or o.startswith("*") or o.startswith("="):
        return None, None, False
    base = o
    index = None
    if "(" in o:
        base = o[:o.index("(")]
        inner = o[o.index("(") + 1:o.rindex(")")] if ")" in o else o[o.index("(") + 1:]
        first = inner.split(",")[0].strip()
        if not first:
            return None, None, True
        index = first
    sym = base
    for sep in ("+", "-"):
        if sep in sym:
            sym = sym.split(sep)[0]
    if not _is_symbol(sym):
        return None, None, True
    return sym.upper(), index, False


class _Branch:
    __slots__ = ("kind", "label", "index", "conditional", "register", "reg_target")

    def __init__(self, kind, label=None, index=None, conditional=False, register=None, reg_target=None):
        self.kind = kind  # perform, goto, count, index, bctr, return, none
        self.label = label
        self.index = index
        self.conditional = conditional
        self.register = register
        self.reg_target = reg_target


def _branch(st: Stmt) -> Optional[_Branch]:
    op = st.op
    ops = st.ops
    if op in NO_BRANCH:
        return None
    if op in BAL_OPS and len(ops) >= 2:
        label, index, regb = _target(ops[1])
        return _Branch("perform", label, index, register=ops[0].upper()) if label else None
    if op in COUNT_LOOP and len(ops) >= 2:
        label, index, regb = _target(ops[-1])
        return _Branch("count", label, index, conditional=True) if label else None
    if op in INDEX_LOOP and len(ops) >= 3:
        label, index, regb = _target(ops[-1])
        return _Branch("index", label, index, conditional=True) if label else None
    if op in ("BCTR", "BCTGR") and len(ops) >= 2:
        reg = ops[1].strip().upper()
        if reg in ("0", "R0"):
            return None
        return _Branch("bctr", reg_target=reg, conditional=True)
    if op in RETURN_OPS:
        return _Branch("return")
    if op == "BCR" and len(ops) >= 2:
        mask = ops[0].strip()
        reg = ops[1].strip().upper()
        if mask == "0" or reg in ("0", "R0"):
            return None
        return _Branch("return") if mask == "15" else None
    if op in UNCOND and ops:
        label, index, regb = _target(ops[0])
        if regb:
            return _Branch("return") if op == "B" else None
        return _Branch("goto", label, index, conditional=False) if label else None
    if op in MASK_BRANCH and len(ops) >= 2:
        mask = ops[0].strip()
        if mask == "0":
            return None
        label, index, regb = _target(ops[1])
        if regb:
            return _Branch("return") if mask == "15" else None
        return _Branch("goto", label, index, conditional=mask != "15") if label else None
    for base in COMPARE_BRANCH:
        if op.startswith(base) and (op == base or op[len(base):] in COND_SUFFIX) and ops:
            label, index, regb = _target(ops[-1])
            return _Branch("goto", label, index, conditional=True) if label else None
    mn = _branch_mnemonic(op)
    if mn and mn[0] != "rr" and ops:
        label, index, regb = _target(ops[0])
        return _Branch("goto", label, index, conditional=True) if label else None
    return None


# --------------------------------------------------------------------------- the scanner
class _Source:
    __slots__ = ("path", "file", "copybook")

    def __init__(self, path: Path, file: str, copybook: Optional[str]):
        self.path, self.file, self.copybook = path, file, copybook


class _Scanner:
    def __init__(self, path: Path, include_dirs: Sequence, root: Path):
        z = _z()
        self.z = z
        self.root = root
        self.path = path
        self.index = _member_index(include_dirs)
        self.sources: List[_Source] = [_Source(path, z.rel(path, root), None)]
        self.stmts: List[Stmt] = []
        self.copybooks: List[dict] = []
        self.macro_defs: List[dict] = []
        self.warnings: List[dict] = []
        self.sql_includes: List[str] = []
        self.unresolved_copies: Set[int] = set()  # id() of COPY statements whose member was not found

    # ---- helpers
    def warn(self, st: Optional[Stmt], message: str) -> None:
        if st is None:
            self.warnings.append({"file": self.sources[0].file, "line": None, "message": message})
        else:
            self.warnings.append({"file": self.sources[st.src].file, "line": st.line, "message": message})

    def where(self, st: Stmt) -> dict:
        cb = self.sources[st.src].copybook
        return {"copybook": cb} if cb else {}

    def file_of(self, st: Stmt) -> str:
        return self.sources[st.src].file

    def resolve(self, name: str, near: Path) -> Optional[Path]:
        found = self.index.get(name.upper())
        if not found:
            return None
        ranked = _ranked(found, near, self.path)
        return ranked[0] if ranked else None

    # ---- pass 1: statements with COPY members expanded
    def load(self, path: Path, src: int, chain: Tuple[str, ...], nested_in: Optional[str]) -> None:
        z = self.z
        file = self.sources[src].file
        text = z.read_text(path)
        warns: List[dict] = []
        stmts, defs = open_code(logical_statements(text.splitlines(), file, warns), file, warns)
        self.warnings.extend(warns)
        for d in defs:
            d = dict(d)
            if self.sources[src].copybook:
                d["copybook"] = self.sources[src].copybook
            self.macro_defs.append(d)
        for st in stmts:
            st.src = src
            st.ops = [] if st.op == "EXEC" else split_operands(st.operand)
            self.stmts.append(st)
            member = None
            library = None
            if st.op == "COPY" and st.ops:
                member = st.ops[0].strip().strip("'").upper()
            elif st.op == "EXEC":
                words = st.operand.split()
                if len(words) >= 3 and words[0].upper() == "SQL" and words[1].upper() == "INCLUDE":
                    member = words[2].strip("'\"").upper()
                    library = "SQL INCLUDE"
                    if member not in self.sql_includes:
                        self.sql_includes.append(member)
                    if member in ("SQLCA", "SQLDA"):
                        member = None
            if not member:
                continue
            resolved = self.resolve(member, path)
            rec = {"name": member, "library": library, "resolved": z.rel(resolved, self.root) if resolved else None,
                   "replacing": False, "line": st.line, "nested_in": nested_in, "replacing_pairs": []}
            self.copybooks.append(rec)
            if resolved is None:
                self.unresolved_copies.add(id(st))
                self.warn(st, f"COPY member {member} not found"
                              + (f" (COPY in {nested_in})" if nested_in else "")
                              + "; its definitions and code are missing from this map")
                continue
            if member in chain:
                self.warn(st, f"COPY {member} copies itself through {' > '.join(chain)}; not expanded again")
                continue
            if len(chain) > MAX_COPY_DEPTH:
                self.warn(st, f"COPY {member} nested deeper than {MAX_COPY_DEPTH} levels; not expanded")
                continue
            self.sources.append(_Source(resolved, z.rel(resolved, self.root), member))
            self.load(resolved, len(self.sources) - 1, chain + (member,), member)

    # ---- the whole program
    def run(self) -> dict:
        z = self.z
        path = self.path
        member = z.member_name(path)
        self.load(path, 0, (member,), None)
        stmts = [s for s in self.stmts if s.op not in LISTING]
        for k, st in enumerate(stmts):
            st.idx = k
        self.stmts = stmts
        inline = {d["name"] for d in self.macro_defs if d["name"]}
        for st in stmts:
            st.kind = _kind(st, inline)
        self.check_open_code()
        sections = self.sections()
        labels = self.labels()
        paragraphs = self.paragraphs(sections)
        items, equates = self.data_items(sections)
        files, rpl_owner = self.files()
        branches = {st.idx: b for st in stmts if st.kind in ("instruction", "macro")
                    for b in [_branch(st)] if b is not None}
        loops = self.loops(branches, labels)
        self.loop_membership(loops, branches, labels)
        performs, gotos = self.flow(branches, labels)
        literal = self.literal_values(items)
        calls = self.calls(literal)
        self.file_io(files, rpl_owner)
        sql, cics = self.exec_blocks(literal)
        macros = self.macros(inline)
        statements = []
        for st in stmts:
            rec = {"verb": self.verb(st), "line": st.line, "end_line": st.end_line, "paragraph": st.para,
                   "operands": self.operands(st), "in_loop": st.loop, "label": st.label, "kind": st.kind}
            rec.update(self.where(st))
            statements.append(rec)
        pid = self.program_id(member)
        usings = []
        entries = []
        externals = []
        for st in stmts:
            if st.op in ("USING", "DROP"):
                rec = {"verb": st.op, "line": st.line, "operands": list(st.ops), "paragraph": st.para,
                       "label": st.label}
                rec.update(self.where(st))
                usings.append(rec)
            elif st.op == "ENTRY":
                for o in st.ops:
                    if _is_symbol(o.strip()):
                        entries.append(dict({"name": o.strip().upper(), "line": st.line}, **self.where(st)))
            elif st.op in ("EXTRN", "WXTRN"):
                for o in st.ops:
                    name = o.strip()
                    if name.upper().startswith("PART("):
                        continue
                    if _is_symbol(name):
                        externals.append(dict({"name": name.upper(), "line": st.line, "kind": st.op}, **self.where(st)))
        loop_list = []
        for lp in loops:
            via = stmts[lp["via"]]
            top = stmts[lp["start"]]
            rec = {"line": via.line, "file": self.file_of(via), "opcode": via.op,
                   "top": top.label.upper() if lp["type"] != "do" and top.label else None,
                   "start_line": top.line, "end_line": stmts[lp["end"]].end_line, "type": lp["type"],
                   "confidence": lp["confidence"]}
            rec.update(self.where(via))
            loop_list.append(rec)
        text = z.read_text(path)
        return {
            "id": pid, "file": self.sources[0].file, "sha256": z.sha256_file(path), "format": "fixed",
            "lines": len(text.splitlines()), "language": LANGUAGE,
            "partial": any(cb["resolved"] is None for cb in self.copybooks),
            "copybooks": self.copybooks + self.macro_copybooks(macros), "files": files, "data_items": items,
            "paragraphs": paragraphs, "sections": [self.section_record(s) for s in sections],
            "performs": performs, "calls": calls, "gotos": gotos, "sql": sql, "cics": cics, "conditions": [],
            "statements": statements, "procedure_using": [], "procedure_using_line": None,
            "sql_includes": list(self.sql_includes), "warnings": self.warnings,
            "macros": macros, "macro_definitions": self.macro_defs, "equates": equates, "usings": usings,
            "entries": entries, "externals": externals, "loops": loop_list,
        }

    # ---- reporting helpers
    def verb(self, st: Stmt) -> str:
        if st.op == "EXEC":
            word = st.operand.split()[0].upper() if st.operand.split() else "?"
            return f"EXEC {word}"
        return st.op

    def operands(self, st: Stmt) -> List[str]:
        if st.op != "EXEC":
            return list(st.ops)
        words = st.operand.split()
        if not words:
            return []
        if words[0].upper() == "SQL":
            return [self.z.parse_sql(" ".join(words[1:]))["verb"]]
        if words[0].upper() == "CICS":
            return [self.z.parse_cics(" ".join(words[1:]))["command"]]
        return [w.upper() for w in words[1:2]]

    def program_id(self, member: str) -> str:
        for st in self.stmts:
            if st.op in ("CSECT", "RSECT", "START") and _is_symbol(st.label):
                return st.label.upper()
            if st.op == "ENTRY":
                for o in st.ops:
                    if _is_symbol(o.strip()):
                        return o.strip().upper()
        return member

    def check_open_code(self) -> None:
        cond = [st for st in self.stmts if st.kind == "conditional"]
        if cond:
            first = cond[0]
            self.warn(first, f"conditional assembly in open code ({len(cond)} statements: AIF, AGO, SETx...) is not "
                             f"evaluated; statements on every path are in the map")
        for st in self.stmts:
            if st.op == "OPSYN":
                self.warn(st, "OPSYN renames an operation code; the map reads operation codes as written")

    # ---- sections and labels
    def sections(self) -> List[dict]:
        out: List[dict] = []
        cur: Optional[dict] = None
        modes: Dict[str, Dict[str, str]] = {}
        for st in self.stmts:
            if st.op in ("AMODE", "RMODE") and st.ops:
                modes.setdefault((st.label or "").upper(), {})[st.op.lower()] = st.ops[0].strip().upper()
            if st.op in SECTION_OPS:
                if cur is not None:
                    cur["end"] = st.idx - 1
                name = st.label.upper() if _is_symbol(st.label) else None
                kind = "CSECT" if st.op == "START" else st.op
                cur = {"name": name, "kind": st.op, "data_kind": kind, "start": st.idx, "end": st.idx}
                out.append(cur)
            elif st.op == "END" and cur is not None:
                cur["end"] = st.idx - 1
                cur = None
            if cur is not None:
                st.sect = len(out) - 1
                cur["end"] = st.idx
        for s in out:
            s.update(modes.get(s["name"] or "", {}))
        return out

    def section_record(self, s: dict) -> dict:
        start = self.stmts[s["start"]]
        end = self.last_same_file(s["start"], s["end"])
        rec = {"name": s["name"], "kind": s["kind"], "start_line": start.line, "end_line": end.end_line}
        for key in ("amode", "rmode"):
            if key in s:
                rec[key] = s[key]
        rec.update(self.where(start))
        return rec

    def last_same_file(self, a: int, b: int) -> Stmt:
        src = self.stmts[a].src
        for k in range(b, a - 1, -1):
            if self.stmts[k].src == src:
                return self.stmts[k]
        return self.stmts[a]

    def labels(self) -> Dict[str, int]:
        out: Dict[str, int] = {}
        skip = {"AMODE", "RMODE", "TITLE", "USING", "DROP", "OPSYN", "ALIAS", "XATTR", "ACONTROL", "CATTR", "COPY"}
        for st in self.stmts:
            if _is_symbol(st.label) and st.op not in skip and st.kind != "conditional":
                out.setdefault(st.label.upper(), st.idx)
        return out

    def _data_macro(self, st: Stmt) -> bool:
        return st.kind == "macro" and (st.op in DATA_MACROS or _list_form(st.operand))

    def _zero_h(self, st: Stmt) -> bool:
        if st.op != "DS" or len(st.ops) != 1:
            return False
        c = parse_constant(st.ops[0])
        return c is not None and c["dup"] == 0 and c["type"] == "H" and not c["explicit"]

    def paragraphs(self, sections: List[dict]) -> List[dict]:
        out: List[dict] = []
        cur: Optional[dict] = None
        current_sect = None

        def close(k: int) -> None:
            nonlocal cur
            if cur is not None:
                cur["_end"] = k
                out.append(cur)
            cur = None

        for st in self.stmts:
            in_dsect = st.sect is not None and sections[st.sect]["kind"] == "DSECT"
            if st.sect != current_sect:
                close(st.idx - 1)
                current_sect = st.sect
            starts = False
            ends = False
            if _is_symbol(st.label) and not in_dsect:
                if st.kind in ("instruction", "exec") or (st.kind == "macro" and not self._data_macro(st)):
                    starts = True
                elif self._zero_h(st) or (st.op == "EQU" and st.operand.strip() == "*"):
                    starts = True
                elif st.op in ("DS", "DC") or self._data_macro(st):
                    ends = True
            if st.op in SECTION_OPS or st.op == "END":
                ends = True
            if starts:
                close(st.idx - 1)
                sect_name = sections[st.sect]["name"] if st.sect is not None else None
                cur = {"name": st.label.upper(), "section": sect_name, "_start": st.idx}
            elif ends:
                close(st.idx - 1)
            st.para = cur["name"] if cur is not None else None
        close(len(self.stmts) - 1)
        records = []
        for p in out:
            start = self.stmts[p["_start"]]
            end = self.last_same_file(p["_start"], max(p["_start"], p["_end"]))
            rec = {"name": p["name"], "section": p["section"], "start_line": start.line, "end_line": end.end_line}
            rec.update(self.where(start))
            records.append(rec)
        return records

    # ---- data
    def data_items(self, sections: List[dict]) -> Tuple[List[dict], List[dict]]:
        """DS and DC records, and EQU records.

        Positions follow the location counter of each control section: from 0 at the
        section start, with the boundary alignment of F, H, D, A... When a length is an
        expression, or code of unknown length comes between, the counter is lost; the next
        field starts a new relative count (its offset is then null). A `DS 0CLn` group
        holds the fields whose position falls inside its n bytes.
        """
        items: List[dict] = []
        equates: List[dict] = []
        states: Dict[Any, dict] = {}
        dsect_item: Dict[str, int] = {}

        def state_for(key: Any) -> dict:
            if key not in states:
                states[key] = {"rel": 0, "align": 8, "anchor": 0, "absolute": True, "high": 0, "complete": True,
                               "labels": {}, "groups": [], "redefines": None}
            return states[key]

        def lose(s: dict) -> None:
            s["rel"] = None
            s["complete"] = False

        def reanchor(s: dict, align: int) -> None:
            s.update(rel=0, align=align, anchor=s["anchor"] + 1, absolute=False, high=0, groups=[])

        for st in self.stmts:
            sect = self.section_of(st, sections)
            key = (sect["name"], sect["kind"]) if sect else None
            s = state_for(key)
            sect_name = sect["name"] if sect else None
            in_dsect = bool(sect and sect["kind"] == "DSECT")
            if st.op in SECTION_OPS:
                s["redefines"] = None
                if in_dsect and sect_name and sect_name not in dsect_item:
                    rec = self.item(st, 1, sect_name, None, None, "DSECT", None, None, sect_name)
                    rec["offset"] = 0
                    dsect_item[sect_name] = len(items)
                    items.append(rec)
                continue
            if st.op == "EQU":
                if _is_symbol(st.label):
                    rec = {"name": st.label.upper(), "value": st.operand, "line": st.line,
                           "control_section": sect_name, "file": self.file_of(st)}
                    rec.update(self.where(st))
                    equates.append(rec)
                    if st.operand.strip() == "*" and s["rel"] is not None:
                        s["labels"][st.label.upper()] = (s["anchor"], s["rel"])
                continue
            if st.op == "ORG":
                self.org(st, s)
                continue
            if st.op == "CNOP":
                nums = [_int(o) for o in st.ops]
                if s["rel"] is not None and len(nums) == 2 and None not in nums and nums[1] and s["align"] >= nums[1]:
                    while s["rel"] % nums[1] != nums[0] % nums[1]:
                        s["rel"] += 1
                else:
                    lose(s)
                    s["groups"] = []
                continue
            if s["rel"] is not None:  # groups whose bytes are all placed are complete
                while s["groups"] and s["rel"] >= s["groups"][-1][2]:
                    s["groups"].pop()
            if st.op not in ("DS", "DC"):
                if (st.kind == "macro" and _is_symbol(st.label) and self._data_macro(st)
                        and st.op not in ("DCB", "ACB", "RPL")):
                    # a parameter list (MF=L) or control block: storage of a length this reader does not know
                    if s["groups"]:
                        parent, level = s["groups"][-1][0], items[s["groups"][-1][0]]["level"] + 1
                    elif in_dsect and sect_name in dsect_item:
                        parent, level = dsect_item[sect_name], 2
                    else:
                        parent, level = None, 1
                    rec = self.item(st, level, st.label.upper(), items[parent]["name"] if parent is not None else None,
                                    parent, sect["data_kind"] if sect else None, None, None, sect_name)
                    rec["usage"] = (f"parameter list ({st.op} MF=L)" if _list_form(st.operand)
                                    else f"control block ({st.op})")
                    rec["definition"] = st.operand
                    items.append(rec)
                unresolved_copy = st.op == "COPY" and id(st) in self.unresolved_copies
                if unresolved_copy or (st.kind in ("instruction", "macro", "exec") and st.op not in EQU_MACROS) \
                        or st.op in ("LTORG", "CCW", "CCW0", "CCW1", "DXD", "CXD"):
                    lose(s)
                    s["groups"] = []  # code, or storage of unknown length, ends any group
                continue
            if self._zero_h(st) and _is_symbol(st.label) and not in_dsect:
                lose(s)
                s["groups"] = []  # a branch target, not storage
                continue
            consts = [parse_constant(o) for o in st.ops]
            first = consts[0] if consts else None
            name = st.label.upper() if _is_symbol(st.label) else "FILLER"
            if first is None:
                if name != "FILLER":
                    parent = dsect_item.get(sect_name) if in_dsect else None
                    rec = self.item(st, 2 if parent is not None else 1, name,
                                    items[parent]["name"] if parent is not None else None, parent,
                                    sect["data_kind"] if sect else None, None, None, sect_name)
                    items.append(rec)
                    self.warn(st, f"{st.op} operand {st.operand[:40]} is not understood; its type and length are unknown")
                lose(s)
                s["groups"] = []
                continue
            # where the field starts
            align = first["align"]
            if s["rel"] is None:
                if s["groups"]:
                    self.warn(st, f"the position of {name} is not known (a length before it is an expression); "
                                  f"it is not placed in group {items[s['groups'][-1][0]]['name']}")
                reanchor(s, align)
            elif align > 1:
                if s["align"] >= align:
                    s["rel"] = -(-s["rel"] // align) * align
                else:
                    if s["groups"]:
                        self.warn(st, f"the boundary alignment of {name} is not known here; it is not placed in "
                                      f"group {items[s['groups'][-1][0]]['name']}")
                    reanchor(s, align)
            start = s["rel"]
            while s["groups"] and not (s["groups"][-1][1] <= start < s["groups"][-1][2]):
                s["groups"].pop()
            # where it ends
            rel: Optional[int] = start
            total: Optional[int] = 0
            for c in consts:
                if c is None or c["size"] is None:
                    rel = total = None
                    break
                if c is not first and c["align"] > 1:
                    if s["align"] < c["align"]:
                        rel = total = None
                        break
                    rel = -(-rel // c["align"]) * c["align"]
                rel += c["size"]
                total += c["size"]
            header = first["dup"] == 0 and first["explicit"] and first["length"] is not None
            if not header and len(consts) == 1 and first["size"] == 0 and name == "FILLER":
                continue  # DS 0F with no name: alignment only
            if s["groups"]:
                parent = s["groups"][-1][0]
                level = items[parent]["level"] + 1
            elif in_dsect and sect_name in dsect_item:
                parent = dsect_item[sect_name]
                level = 2
            else:
                parent, level = None, 1
            occurs = None
            if isinstance(first["dup"], int) and first["dup"] > 1:
                occurs = {"min": first["dup"], "max": first["dup"], "depending_on": None, "keys": [], "indexed_by": []}
            rec = self.item(st, level, name, items[parent]["name"] if parent is not None else None, parent,
                            sect["data_kind"] if sect else None, first, occurs, sect_name)
            rec["redefines"] = s["redefines"]
            s["redefines"] = None
            rec["size"] = first["length"] if header else total
            rec["offset"] = start if s["absolute"] else None
            if name != "FILLER":
                s["labels"].setdefault(name, (s["anchor"], start))
            items.append(rec)
            if header:
                s["groups"].append((len(items) - 1, start, start + first["length"]))
            if rel is None:
                lose(s)
            else:
                s["rel"] = rel
                s["high"] = max(s["high"], rel)
        for (key, s) in states.items():
            if key and key[1] == "DSECT" and key[0] in dsect_item:
                items[dsect_item[key[0]]]["size"] = s["high"] if s["absolute"] and s["complete"] else None
        return items, equates

    @staticmethod
    def section_of(st: Stmt, sections: List[dict]) -> Optional[dict]:
        return sections[st.sect] if st.sect is not None else None

    def org(self, st: Stmt, s: dict) -> None:
        """ORG: back to a label (the next field redefines it), forward by *+n, or to the highest point."""
        expr = st.ops[0].strip() if st.ops else ""
        if s["rel"] is not None:
            s["high"] = max(s["high"], s["rel"])
        if not expr:
            s["redefines"] = None
            if s["rel"] is not None:
                s["rel"] = s["high"]
            return
        sym, offset = expr, 0
        for sep in ("+", "-"):
            if sep in expr:
                left, right = expr.split(sep, 1)
                if right.strip().isdigit():
                    sym, offset = left.strip(), (int(right) if sep == "+" else -int(right))
                break
        if sym == "*":
            if s["rel"] is not None:
                s["rel"] += offset
                s["high"] = max(s["high"], s["rel"])
            return
        found = s["labels"].get(sym.upper()) if _is_symbol(sym) else None
        s["redefines"] = sym.upper() if _is_symbol(sym) else None
        if found is not None and found[0] == s["anchor"] and found[1] is not None:
            s["rel"] = found[1] + offset
        else:
            s["rel"] = None
            s["complete"] = False
        s["groups"] = [g for g in s["groups"] if s["rel"] is not None and g[1] <= s["rel"] < g[2]]

    def item(self, st: Stmt, level: int, name: str, parent: Optional[str], parent_index: Optional[int],
             section: Optional[str], const: Optional[dict], occurs: Optional[dict], sect_name: Optional[str]) -> dict:
        usage = TYPE_INFO.get(const["type"], (None, 1, None))[2] if const else None
        cb = self.sources[st.src].copybook
        return {"level": level, "name": name, "pic": const["pic"] if const else None, "usage": usage, "occurs": occurs,
                "redefines": None, "value": const["nominal"] if const and st.op == "DC" else None,
                "section": section, "parent": parent, "parent_index": parent_index, "copybook": cb,
                "file": self.file_of(st), "line": st.line, "fd": None,
                "type": const["type"] if const else None, "length": const["length"] if const else None,
                "dup": (const["dup"] if const["dup"] is not None else const["dup_text"]) if const else None,
                "nominal": const["nominal"] if const else None, "size": None, "offset": None,
                "definition": st.operand if st.op in ("DS", "DC") else None, "op": st.op, "control_section": sect_name}

    # ---- files
    def files(self) -> Tuple[List[dict], Dict[str, str]]:
        files: List[dict] = []
        rpl_owner: Dict[str, str] = {}
        rpls: List[Tuple[Stmt, Dict[str, str]]] = []
        for st in self.stmts:
            if st.kind != "macro" or st.op not in ("DCB", "ACB", "RPL") or _list_form(st.operand):
                continue
            _, kw = keywords(st.ops)
            if st.op == "RPL":
                rpls.append((st, kw))
                continue
            if not _is_symbol(st.label):
                self.warn(st, f"{st.op} without a name; it cannot be opened by name and is not mapped as a file")
                continue
            name = st.label.upper()
            dd = kw.get("DDNAME")
            if dd is None and st.op == "ACB":
                dd = name  # VSAM uses the ACB name when DDNAME is left out
            elif dd is None:
                self.warn(st, f"DCB {name} has no DDNAME=; the program sets the DD name at run time")
            rec = {"name": name, "assign": kw.get("DDNAME"), "organization": kw.get("DSORG") if st.op == "DCB" else "VSAM",
                   "access": kw.get("MACRF"), "record": None, "io": [], "dd": dd.upper() if dd else None,
                   "status": None, "keys": [], "records": [], "line": st.line, "kind": st.op,
                   "options": {k: v for k, v in kw.items()}, "rpls": [], "datasets": []}
            rec.update(self.where(st))
            files.append(rec)
        by_name = {f["name"]: f for f in files}
        for st, kw in rpls:
            acb = (kw.get("ACB") or "").upper()
            if _is_symbol(st.label) and acb in by_name:
                rpl = st.label.upper()
                rpl_owner[rpl] = acb
                by_name[acb]["rpls"].append(rpl)
                area = kw.get("AREA")
                if area and _is_symbol(area) and area.upper() not in by_name[acb]["records"]:
                    by_name[acb]["records"].append(area.upper())
        return files, rpl_owner

    def file_io(self, files: List[dict], rpl_owner: Dict[str, str]) -> None:
        by_name = {f["name"]: f for f in files}
        decb: Dict[str, str] = {}

        def hit(st: Stmt, name: str, mode: Optional[str] = None, area: Optional[str] = None) -> None:
            target = name.strip().upper()
            if target.startswith("RPL="):
                target = rpl_owner.get(target[4:], target)
            if target not in by_name:
                how = "a register" if target.startswith("(") else f"{target}, which is not a DCB or ACB here"
                self.warn(st, f"{st.op} names {how}; the file is not known")
                return
            io = {"verb": st.op, "line": st.line, "paragraph": st.para, "in_loop": st.loop}
            if mode:
                io["mode"] = mode
            io.update(self.where(st))
            by_name[target]["io"].append(io)
            if area and _is_symbol(area.strip()):
                rec = by_name[target]
                a = area.strip().upper()
                if a not in rec["records"]:
                    rec["records"].append(a)
                if rec["record"] is None:
                    rec["record"] = a

        for st in self.stmts:
            if st.kind != "macro" or _list_form(st.operand):
                continue
            pos, kw = keywords(st.ops)
            if st.op in ("OPEN", "CLOSE"):
                if not pos or not pos[0]:
                    continue
                inner = _inner(pos[0])
                entries = split_operands(inner) if inner is not None else [pos[0]]
                for k in range(0, len(entries), 2):
                    dcb = entries[k].strip()
                    if not dcb:
                        continue
                    opts = entries[k + 1].strip() if k + 1 < len(entries) else ""
                    words = [w.strip().upper() for w in (_inner(opts) or opts).split(",") if w.strip()]
                    mode = next((w for w in words if w in OPEN_MODES), None) if st.op == "OPEN" else None
                    hit(st, dcb, mode)
            elif st.op in IO_FIRST:
                if "RPL" in kw:
                    hit(st, "RPL=" + kw["RPL"].upper())
                elif pos and pos[0].strip():
                    hit(st, pos[0], None, pos[1] if st.op in ("GET", "PUT", "PUTX") and len(pos) > 1 else None)
            elif st.op in ("READ", "WRITE") and len(pos) >= 3:
                if _is_symbol(pos[0].strip()):
                    decb[pos[0].strip().upper()] = pos[2].strip().upper()
                hit(st, pos[2], None, pos[3] if len(pos) > 3 else None)
            elif st.op == "CHECK" and pos:
                owner = decb.get(pos[0].strip().upper())
                if owner:
                    hit(st, owner)

    # ---- flow
    def flow(self, branches: Dict[int, _Branch], labels: Dict[str, int]) -> Tuple[List[dict], List[dict]]:
        performs: List[dict] = []
        gotos: List[dict] = []
        warned: Set[str] = set()
        for k, b in sorted(branches.items()):
            st = self.stmts[k]
            if b.kind == "perform":
                if b.label not in labels and b.label not in warned:
                    warned.add(b.label)
                    self.warn(st, f"{st.op} target {b.label} is not a label in this module (a macro, a missing COPY "
                                  f"member or an external name)")
                rec = {"from": st.para, "to": b.label, "thru": None, "loop": None, "inline": False, "line": st.line,
                       "end_line": st.end_line, "in_loop": st.loop, "opcode": st.op, "register": b.register}
                rec.update(self.where(st))
                performs.append(rec)
            elif b.kind in ("goto", "count", "index"):
                if b.label not in labels and b.label not in warned:
                    warned.add(b.label)
                    self.warn(st, f"branch target {b.label} is not a label in this module (a macro, a missing COPY "
                                  f"member or an external name)")
                if b.index:
                    self.warn(st, f"{st.op} {st.operand}: a computed branch, the target depends on {b.index}")
                target = labels.get(b.label)
                rec = {"to": [b.label], "line": st.line, "paragraph": st.para, "depending_on": b.index,
                       "opcode": st.op, "conditional": b.conditional,
                       "backward": (target <= k) if target is not None else None}
                rec.update(self.where(st))
                gotos.append(rec)
        return performs, gotos

    def loops(self, branches: Dict[int, _Branch], labels: Dict[str, int]) -> List[dict]:
        stmts = self.stmts
        loops: List[dict] = []

        def returns_between(a: int, b: int) -> bool:
            for k in range(a, b):
                x = branches.get(k)
                if x is not None and x.kind == "return":
                    return True
                if stmts[k].op in ("RETURN", "DFHEIRET", "CEETERM"):
                    return True
            return False

        for k, b in sorted(branches.items()):
            st = stmts[k]
            if b.kind == "bctr":
                target = None
                for j in range(k - 1, max(-1, k - 1 - BCTR_LOOKBACK), -1):
                    prev = stmts[j]
                    if prev.sect != st.sect:
                        break
                    if prev.op in ("LA", "LARL", "LAY") and len(prev.ops) >= 2 and prev.ops[0].strip().upper() == b.reg_target:
                        label, index, regb = _target(prev.ops[1])
                        target = labels.get(label) if label and not index else None
                        break
                if target is not None and target <= k:
                    loops.append({"start": target, "end": k, "via": k, "type": "count", "confidence": "medium"})
                else:
                    self.warn(st, f"{st.op} {st.operand} branches to an address in a register; the loop it closes is "
                                  f"not located")
                continue
            if b.kind not in ("goto", "count", "index") or b.index:
                continue
            t = labels.get(b.label)
            if t is None or t > k:
                continue
            if b.kind in ("count", "index"):
                loops.append({"start": t, "end": k, "via": k, "type": b.kind, "confidence": "high"})
            elif b.conditional:
                if not returns_between(t, k):
                    loops.append({"start": t, "end": k, "via": k, "type": "conditional", "confidence": "medium"})
            else:
                if returns_between(t, k):
                    continue
                exits = False
                for j in range(t, k):
                    x = branches.get(j)
                    if x is not None and x.kind in ("goto", "count", "index") and x.conditional:
                        tj = labels.get(x.label)
                        if tj is not None and tj > k:
                            exits = True
                            break
                if exits:
                    loops.append({"start": t, "end": k, "via": k, "type": "unconditional", "confidence": "low"})
        # structured macros: DO ... ENDDO with WHILE=, UNTIL=, FROM= or INF
        stack: List[Tuple[int, bool]] = []
        for st in stmts:
            if st.op == "DO" and st.kind == "macro":
                words = st.operand.upper()
                stack.append((st.idx, any(w in words for w in ("WHILE", "UNTIL", "FROM", "INF"))))
            elif st.op == "ENDDO" and st.kind == "macro" and stack:
                start, looping = stack.pop()
                if looping:
                    loops.append({"start": start, "end": st.idx, "via": start, "type": "do", "confidence": "high"})
        return loops

    def extent(self, t: int, branches: Dict[int, _Branch]) -> List[int]:
        """Statements a BAL target runs by falling through: to the first return or unconditional branch."""
        out = []
        sect = self.stmts[t].sect
        for k in range(t, len(self.stmts)):
            st = self.stmts[k]
            if k > t and (st.op in SECTION_OPS or st.op == "END" or st.sect != sect):
                break
            if k > t and _is_symbol(st.label) and st.op in ("DS", "DC") and not self._zero_h(st):
                break
            out.append(k)
            b = branches.get(k)
            if st.op in FLOW_END or (b is not None and (b.kind == "return" or (b.kind == "goto" and not b.conditional))):
                break
        return out

    def loop_membership(self, loops: List[dict], branches: Dict[int, _Branch], labels: Dict[str, int]) -> None:
        stmts = self.stmts

        def record(lp: dict) -> dict:
            via = stmts[lp["via"]]
            return {"via": via.line, "kind": "do" if lp["type"] == "do" else "branch", "file": self.file_of(via),
                    "confidence": lp["confidence"]}

        best: Dict[int, Tuple[int, int, int, dict]] = {}
        for lp in loops:
            size = lp["end"] - lp["start"]
            for k in range(lp["start"], lp["end"] + 1):
                cand = (size, -stmts[lp["via"]].line)
                if k not in best or cand < best[k][:2]:
                    best[k] = (size, -stmts[lp["via"]].line, 0, lp)
        physical = {k: v[3] for k, v in best.items()}
        # calls by BAL from inside a loop: the routine's statements are in that loop too
        bal_targets: Dict[int, List[int]] = {}
        for k, b in branches.items():
            if b.kind == "perform" and b.label in labels:
                bal_targets.setdefault(k, []).append(labels[b.label])
        extents: Dict[int, List[int]] = {}
        reached: Dict[int, Tuple[int, int, int, dict]] = {}
        for lp in loops:
            size = lp["end"] - lp["start"]
            frontier = [k for k in range(lp["start"], lp["end"] + 1) if k in bal_targets]
            seen: Set[int] = set()
            dist = 1
            while frontier:
                nxt: List[int] = []
                for k in frontier:
                    for t in bal_targets.get(k, []):
                        if t in seen:
                            continue
                        seen.add(t)
                        if t not in extents:
                            extents[t] = self.extent(t, branches)
                        for m in extents[t]:
                            if m in physical:
                                continue
                            cand = (dist, size, -stmts[lp["via"]].line)
                            if m not in reached or cand < reached[m][:3]:
                                reached[m] = (dist, size, -stmts[lp["via"]].line, lp)
                            if m in bal_targets:
                                nxt.append(m)
                frontier = nxt
                dist += 1
        for k, st in enumerate(stmts):
            if k in physical:
                st.loop = record(physical[k])
            elif k in reached:
                st.loop = record(reached[k][3])

    def _file_for(self, copybook: str) -> str:
        for s in self.sources:
            if s.copybook == copybook:
                return s.file
        return self.sources[0].file

    # ---- calls, SQL, CICS
    def literal_values(self, items: List[dict]) -> Dict[str, List[str]]:
        """Names a field can hold: its DC C'...' value and MVC field,=C'...' literals."""
        out: Dict[str, List[str]] = {}

        def add(name: str, nominal: str) -> None:
            if not nominal or nominal[0] != "'":
                return
            value = nominal[1:-1] if nominal.endswith("'") and len(nominal) > 1 else nominal[1:]
            value = value.replace("''", "'").strip().upper()
            if value and _is_symbol(value):
                vals = out.setdefault(name, [])
                if value not in vals:
                    vals.append(value)

        for it in items:
            if it.get("op") == "DC" and (it.get("type") or "").startswith("C") and it["name"] != "FILLER":
                add(it["name"], it.get("nominal") or "")
        for st in self.stmts:
            if st.op == "MVC" and len(st.ops) == 2 and _is_symbol(st.ops[0].strip()) and st.ops[1].startswith("="):
                c = parse_constant(st.ops[1][1:])
                if c and c["type"].startswith("C") and c["nominal"]:
                    add(st.ops[0].strip().upper(), c["nominal"])
        return out

    def calls(self, literal: Dict[str, List[str]]) -> List[dict]:
        out: List[dict] = []
        for st in self.stmts:
            base = {"line": st.line, "paragraph": st.para, "in_loop": st.loop}
            if st.kind == "macro" and st.op in CALL_MACROS and not _list_form(st.operand):
                pos, kw = keywords(st.ops)
                target: Optional[str] = None
                dynamic = False
                using: List[str] = []
                candidates: Optional[List[str]] = None
                if st.op == "CALL":
                    entry = pos[0].strip() if pos else ""
                    if not entry:
                        target, dynamic = None, True
                    elif entry.startswith("("):
                        target, dynamic = entry.upper(), True
                    else:
                        target = entry.upper()
                    if len(pos) > 1 and _inner(pos[1]) is not None:
                        using = [x.strip().upper() if _is_symbol(x.strip()) else x.strip()
                                 for x in split_operands(_inner(pos[1]) or "") if x.strip()]
                else:
                    if "EP" in kw and not kw["EP"].startswith("("):
                        target = kw["EP"].strip().upper()
                    elif "EP" in kw:
                        target, dynamic = kw["EP"].strip().upper(), True
                    elif "EPLOC" in kw:
                        target, dynamic = kw["EPLOC"].strip().upper(), True
                        if _is_symbol(target):
                            candidates = list(literal.get(target, []))
                    elif "DE" in kw:
                        target, dynamic = kw["DE"].strip().upper(), True
                    else:
                        target, dynamic = None, True
                    param = kw.get("PARAM")
                    if param and _inner(param) is not None:
                        using = [x.strip().upper() if _is_symbol(x.strip()) else x.strip()
                                 for x in split_operands(_inner(param) or "") if x.strip()]
                if target is None:
                    self.warn(st, f"{st.op} names no entry point (execute form with a list built elsewhere); the "
                                  f"target is not known")
                rec = {"target": target, "dynamic": dynamic, **base, "using": using, "kind": st.op}
                if dynamic:
                    rec["candidates"] = candidates if candidates is not None else []
                rec.update(self.where(st))
                out.append(rec)
                continue
            if "V(" in st.operand.upper() and st.kind in ("instruction", "data", "macro"):
                for name in _vcon_names(st):
                    rec = {"target": name, "dynamic": False, **base, "using": [], "kind": "V-con"}
                    rec.update(self.where(st))
                    out.append(rec)
        return out

    def exec_blocks(self, literal: Dict[str, List[str]]) -> Tuple[List[dict], List[dict]]:
        z = self.z
        sql: List[dict] = []
        cics: List[dict] = []
        cursor_tables: Dict[str, List[str]] = {}
        for st in self.stmts:
            if st.op != "EXEC":
                continue
            words = st.operand.split()
            if not words:
                continue
            body = " ".join(words[1:])
            if words[0].upper() == "SQL":
                s = z.parse_sql(body)
                rec = {"line": st.line, "end_line": st.end_line, "paragraph": st.para, "verb": s["verb"],
                       "tables": s["tables"], "cursor": s["cursor"], "host_vars": s["host_vars"],
                       "multi_row": s["multi_row"], "text": body, "in_loop": st.loop}
                rec.update(self.where(st))
                sql.append(rec)
                if s["verb"] == "DECLARE CURSOR" and s["cursor"]:
                    cursor_tables[s["cursor"]] = s["tables"]
            elif words[0].upper() == "CICS":
                c = z.parse_cics(body)
                rec = {"line": st.line, "end_line": st.end_line, "paragraph": st.para, "command": c["command"],
                       "options": c["options"], "in_loop": st.loop}
                prog = c["options"].get("program")
                if isinstance(prog, str) and prog[:1] not in ("'", '"'):
                    rec["candidates"] = list(literal.get(prog.strip().upper(), []))
                rec.update(self.where(st))
                cics.append(rec)
        for s in sql:
            if s["cursor"] and not s["tables"] and s["cursor"] in cursor_tables:
                s["tables"] = list(cursor_tables[s["cursor"]])
        return sql, cics

    # ---- macros
    def macros(self, inline: Set[str]) -> List[dict]:
        out: Dict[str, dict] = {}
        inline_def = {}
        for d in self.macro_defs:
            if d["name"] and d["name"] not in inline_def:
                inline_def[d["name"]] = d
        for st in self.stmts:
            if st.kind != "macro":
                continue
            name = st.op
            rec = out.get(name)
            if rec is None:
                rec = {"name": name, "found": False, "definition": None, "definition_line": None, "inline": False,
                       "system": name in SYSTEM_MACROS, "count": 0, "line": st.line}
                rec.update(self.where(st))
                if name in inline_def:
                    d = inline_def[name]
                    rec.update(found=True, inline=True, definition_line=d["start_line"],
                               definition=self._file_for(d["copybook"]) if d.get("copybook") else self.sources[0].file)
                elif not name.startswith("&"):
                    lib = self.library_macro(name)
                    if lib is not None:
                        rec.update(found=True, definition=self.z.rel(lib, self.root),
                                   definition_line=_macros_in_file(lib).get(name))
                out[name] = rec
            rec["count"] += 1
        return list(out.values())

    def library_macro(self, name: str) -> Optional[Path]:
        found = self.index.get(name.upper())
        if not found:
            return None
        for p in _ranked(found, self.path, self.path):
            if name.upper() in _macros_in_file(p):
                return p
        return None

    def macro_copybooks(self, macros: List[dict]) -> List[dict]:
        out = []
        for m in macros:
            if m["found"] and not m["inline"]:
                out.append({"name": m["name"], "library": "MACRO", "resolved": m["definition"], "replacing": False,
                            "line": m["line"], "nested_in": m.get("copybook"), "replacing_pairs": []})
        return out


def _vcon_names(st: Stmt) -> List[str]:
    """External names of V-type address constants: DC V(A,B) and =V(A) literals."""
    names: List[str] = []
    for o in st.ops:
        text = o.strip()
        if text.startswith("="):
            text = text[1:]
        elif st.op != "DC":
            continue
        c = parse_constant(text)
        if c is None or not c["type"].startswith("V") or not c["nominal"] or c["nominal"][0] != "(":
            continue
        for v in c["values"]:
            v = v.strip()
            if _is_symbol(v) and v.upper() not in names:
                names.append(v.upper())
    return names


def scan_program(path, include_dirs: Sequence = (), root=None) -> dict:
    """One Assembler member as a program record (contract version 1, language "asm").

    `include_dirs` are the folders searched by member name for COPY members, EXEC SQL
    INCLUDE members and macro definitions. Nothing is written.
    """
    z = _z()
    base = z.project_root(root)
    p = Path(path)
    if not p.is_absolute():
        p = base / p
    return _Scanner(p, [Path(d) if os.path.isabs(str(d)) else base / d for d in include_dirs], base).run()
