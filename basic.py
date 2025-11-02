#!/usr/bin/env python3
"""
PYBASIC 3.0 - All-In-One Retro BASIC Emulator
Author: ChatGPT (GPT-5 Thinking mini)
Run: python pybasic3_allinone.py

Features:
 - Line-numbered editor: LIST, RUN, NEW, SAVE, LOAD, EXIT
 - PRINT, LET, INPUT, IF..THEN, GOTO, FOR..NEXT, GOSUB/RETURN, END, REM
 - Multi-statements per line using ':'
 - Strings and string functions: LEN, LEFT$, RIGHT$, MID$, CHR$, ASC
 - Arrays: DIM A(n), numeric and string arrays
 - PEEK(addr), POKE(addr,value) (simulated 64K memory)
 - INKEY$(), KEY$ variable (non-blocking), GET (wait for 1 key)
 - RND(), RANDOMIZE TIMER
 - SOUND freq,duration (winsound on Windows or fallback)
 - CLS, LOCATE, PSET, PGET, simple LINE implementation
 - Sprite API: SPRITE id CREATE/DRAW/MOVE/CLEAR/DEL
 - AUTO and RENUM utilities
 - FILES listing and .bas SAVE/LOAD
 - TRACE (show executed lines), TIMER, FRE (free bytes)
 - Error handling with classic-style messages
 - Demos auto-created in bas_games/
"""

import os, sys, re, time, random, math, json, glob
from collections import defaultdict

# ---------------- Configuration ----------------
SCREEN_ROWS = 24
SCREEN_COLS = 80
GAME_FOLDER = "bas_games"
VERSION = "PYBASIC 3.0 - All-In-One"
MEMORY_SIZE = 65536  # 64KB simulated
AUTO_STEP_DEFAULT = 10

# Windows curses helper note
try:
    import curses
except Exception:
    curses = None

# ---------------- Global State ----------------
program = {}           # {line_number: code}
variables = {}         # scalar variables (numbers/strings)
string_vars = set()    # names ending with $
arrays = {}            # arrays storage: arrays['A'] = list, arrays['A$'] for string arrays
stack = []             # FOR / GOSUB stack
pc_index = 0
running_program = False
screen_win = None
screen_buf = None
cursor_r = 1
cursor_c = 1
sprites = {}           # sprite_id -> {x,y,pattern}
last_key = None
key_buffer = []
memory = bytearray(MEMORY_SIZE)
random.seed(int(time.time()*1000) & 0xFFFFFFFF)
auto_mode = False
next_auto_line = 10
auto_step = AUTO_STEP_DEFAULT
trace_mode = False
boot_time = time.time()

# ---------------- Utilities & Error Handling ----------------
class BasicError(Exception):
    pass

def basic_error(msg, line=None):
    if line is not None:
        raise BasicError(f"?{msg} IN LINE {line}")
    else:
        raise BasicError(f"?{msg}")

def human(n):
    return int(n) if int(n) == n else n

def is_string_var(name):
    return name.endswith('$')

# ---------------- Safe Eval & Expression Handling ----------------
# We'll preprocess BASIC expression syntax and supply a controlled eval environment.
_ident_re = re.compile(r'[A-Za-z_]\w*\$?')

def __ARR__(name, idx):
    """Helper for array access in safe_eval replacement."""
    name = str(name)
    idx = int(idx)
    if name in arrays:
        arr = arrays[name]
        if 0 <= idx < len(arr):
            return arr[idx]
        else:
            basic_error("SUBSCRIPT OUT OF RANGE")
    basic_error("VARIABLE NOT DEFINED")

def __SET_ARR__(name, idx, val):
    name = str(name)
    idx = int(idx)
    if name in arrays:
        arr = arrays[name]
        if 0 <= idx < len(arr):
            arr[idx] = val
            return val
        else:
            basic_error("SUBSCRIPT OUT OF RANGE")
    basic_error("VARIABLE NOT DEFINED")

def safe_eval(expr):
    """
    Evaluate a BASIC expression with:
     - ^ mapped to **
     - RND -> rnd()
     - array access A(5) replaced by __ARR__('A',5)
     - functions: INT, ABS, SIN, COS, TAN, CHR$, ASC, LEN, LEFT$, RIGHT$, MID$
    Returns Python types: numbers or strings.
    """
    if expr is None:
        return ""
    e = str(expr).strip()
    if e == "":
        return ""
    # Quick replace ^ with **
    e = re.sub(r'\^', '**', e)
    # Replace RND with rnd()
    e = re.sub(r'\bRND\b', 'rnd()', e, flags=re.I)
    # Replace CHR$ with CHR
    e = re.sub(r'CHR\$\s*\(', 'CHR(', e, flags=re.I)
    # Replace string functions names with python-safe versions
    # We'll provide mapping in eval_locals
    # Transform array access: A(expr) -> __ARR__('A', expr)
    def arr_repl(m):
        name = m.group(1)
        # Only replace function-like patterns where name is followed by '(' and index expression
        return f"__ARR__('{name}',"
    e = re.sub(r'\b([A-Za-z_]\w*\$?)\s*\(', lambda m: arr_repl(m) if m.group(1) in arrays else m.group(0), e)
    # Now build local environment
    eval_locals = {}
    # Provide variables
    for k, v in variables.items():
        eval_locals[k] = v
        eval_locals[k.upper()] = v
    # Provide arrays accessible via __ARR__ wrapper
    eval_locals['__ARR__'] = __ARR__
    eval_locals['__SET_ARR__'] = __SET_ARR__
    # Provide utility functions
    eval_locals.update({
        'rnd': lambda: random.random(),
        'RND': lambda: random.random(),
        'INT': lambda x: int(float(x)),
        'ABS': abs,
        'SIN': math.sin,
        'COS': math.cos,
        'TAN': math.tan,
        'CHR': lambda n: chr(int(n)) if n is not None else '',
        'CHR$': lambda n: chr(int(n)) if n is not None else '',
        'ASC': lambda s: ord(str(s)[0]) if s else 0,
        'LEN': lambda s: len(str(s)),
        'LEFT$': lambda s, n: str(s)[:int(n)],
        'RIGHT$': lambda s, n: str(s)[-int(n):] if int(n) > 0 else '',
        'MID$': lambda s, i, n=None: (str(s)[int(i)-1:int(i)-1+int(n)] if n is not None else str(s)[int(i)-1:]),
        'PEEK': lambda addr: memory[int(addr)],
        'POKE': lambda addr, val: (memory.__setitem__(int(addr), int(val)) or int(val)),
        # Timer in seconds since boot
        'TIMER': lambda: (time.time() - boot_time),
        'TIME': lambda: time.strftime("%H:%M:%S"),
        'FRE': lambda x=0: MEMORY_SIZE - len(json.dumps(program)) - 1000  # rough estimate
    })
    # Evaluate
    try:
        val = eval(e, {"__builtins__": None}, eval_locals)
        return val
    except BasicError:
        raise
    except Exception:
        # fallback: return trimmed string literal if quoted, else raw string
        s = e.strip()
        if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
            return s[1:-1]
        # try to interpret as variable name
        if _ident_re.fullmatch(s):
            # return variable value if exists
            name = s
            if name in variables:
                return variables[name]
            if name.upper() in variables:
                return variables[name.upper()]
            if name in arrays and len(arrays[name]) > 0:
                return arrays[name][0]
        # as last fallback, raise syntax error
        basic_error("SYNTAX ERROR")

# ---------------- Screen & curses helpers ----------------
def init_curses(rows=SCREEN_ROWS, cols=SCREEN_COLS):
    global screen_win, screen_buf, SCREEN_ROWS, SCREEN_COLS, cursor_r, cursor_c
    SCREEN_ROWS = rows; SCREEN_COLS = cols
    if curses is None:
        return
    screen_buf = [[" "]*SCREEN_COLS for _ in range(SCREEN_ROWS)]
    screen_win = curses.initscr()
    curses.noecho(); curses.cbreak(); screen_win.keypad(True)
    try: curses.curs_set(0)
    except: pass
    screen_win.nodelay(True)
    cls()

def restore_curses():
    global screen_win
    if screen_win and curses:
        curses.nocbreak(); screen_win.keypad(False); curses.echo()
        try: curses.curs_set(1)
        except: pass
        curses.endwin()
        screen_win = None

def cls():
    global screen_buf, cursor_r, cursor_c
    if screen_buf is not None:
        for r in range(SCREEN_ROWS):
            for c in range(SCREEN_COLS):
                screen_buf[r][c] = " "
    cursor_r = 1; cursor_c = 1
    flush_screen()

def flush_screen():
    if screen_win is None or curses is None:
        return
    for r in range(SCREEN_ROWS):
        try:
            screen_win.addstr(r, 0, "".join(screen_buf[r][:SCREEN_COLS]))
        except:
            pass
    screen_win.refresh()

def locate(r, c):
    global cursor_r, cursor_c
    cursor_r = max(1, min(SCREEN_ROWS, int(r)))
    cursor_c = max(1, min(SCREEN_COLS, int(c)))

def put_text(s, newline=True):
    """Put text at current cursor (1-based)."""
    global cursor_r, cursor_c
    if s is None: s = ""
    s = str(s)
    r = cursor_r - 1
    c = cursor_c - 1
    for ch in s:
        if ch == "\n":
            r += 1; c = 0
            if r >= SCREEN_ROWS: break
        else:
            if 0 <= r < SCREEN_ROWS and 0 <= c < SCREEN_COLS:
                screen_buf[r][c] = ch
            c += 1
            if c >= SCREEN_COLS:
                c = 0; r += 1
                if r >= SCREEN_ROWS: break
    cursor_r = r+1; cursor_c = c+1
    if newline:
        # move to next line start
        cursor_r += 1; cursor_c = 1
    flush_screen()

def pset(x, y, ch="*"):
    x = int(x); y = int(y)
    if 1 <= y <= SCREEN_ROWS and 1 <= x <= SCREEN_COLS:
        screen_buf[y-1][x-1] = str(ch)[0]
    flush_screen()

def pget(x, y):
    x = int(x); y = int(y)
    if 1 <= y <= SCREEN_ROWS and 1 <= x <= SCREEN_COLS:
        return screen_buf[y-1][x-1]
    return " "

# ---------------- Key handling ----------------
def poll_key():
    """Poll terminal key and update last_key (non-blocking)."""
    global last_key
    if curses is None or screen_win is None:
        return None
    ch = screen_win.getch()
    if ch == -1:
        return None
    if ch == 27:
        last_key = "ESC"
    elif ch in (10,13):
        last_key = "\n"
    elif ch in (curses.KEY_UP,):
        last_key = "UP"
    elif ch in (curses.KEY_DOWN,):
        last_key = "DOWN"
    elif ch in (curses.KEY_LEFT,):
        last_key = "LEFT"
    elif ch in (curses.KEY_RIGHT,):
        last_key = "RIGHT"
    elif ch >= 256:
        last_key = f"KEY{ch}"
    else:
        try:
            last_key = chr(ch)
        except:
            last_key = None
    key_buffer.append((time.time(), last_key))
    if len(key_buffer) > 100:
        key_buffer.pop(0)
    return last_key

def inkey$():
    poll_key()
    return last_key if last_key is not None else ""

def get_key_blocking(prompt=None):
    """Wait for a single key (GET)."""
    if curses is None or screen_win is None:
        k = input("? ")
        return k[0] if k else ""
    if prompt:
        put_text(prompt)
    curses.echo(); curses.nocbreak(); screen_win.nodelay(False)
    try:
        ch = screen_win.getch()
        if ch == -1:
            s = screen_win.getstr().decode('utf-8')
            k = s[0] if s else ""
        else:
            if ch in (10,13): k = "\n"
            else:
                try: k = chr(ch)
                except: k = ""
    finally:
        screen_win.nodelay(True); curses.noecho(); curses.cbreak()
    return k

# ---------------- Sound ----------------
def basic_sound(freq, duration_ms):
    try:
        if sys.platform.startswith("win"):
            import winsound
            winsound.Beep(int(freq), int(duration_ms))
            return
    except Exception:
        pass
    try:
        if curses:
            curses.beep()
    except:
        print("\a", end="", flush=True)
    time.sleep((duration_ms or 200)/1000.0)

# ---------------- Arrays & DIM ----------------
def dim_array(name, size):
    """Declare array; name may end with $ for string arrays."""
    name = str(name)
    size = int(size) + 1  # tradition: allow 0..n
    arrays[name] = [0] * size if not is_string_var(name) else ["" for _ in range(size)]

# ---------------- Sprites ----------------
def sprite_create(sid, x, y, pattern):
    sprites[sid] = {'x':int(x), 'y':int(y), 'pattern':pattern if isinstance(pattern, list) else [str(pattern)], 'visible': True}

def sprite_draw(sid):
    s = sprites.get(sid)
    if not s: return
    for ry, line in enumerate(s['pattern']):
        for cx, ch in enumerate(line):
            rx = s['x'] - 1 + cx
            ry2 = s['y'] - 1 + ry
            if 0 <= ry2 < SCREEN_ROWS and 0 <= rx < SCREEN_COLS:
                screen_buf[ry2][rx] = ch
    flush_screen()

def sprite_clear(sid):
    s = sprites.get(sid)
    if not s: return
    for ry, line in enumerate(s['pattern']):
        for cx, ch in enumerate(line):
            rx = s['x'] - 1 + cx
            ry2 = s['y'] - 1 + ry
            if 0 <= ry2 < SCREEN_ROWS and 0 <= rx < SCREEN_COLS:
                screen_buf[ry2][rx] = " "
    flush_screen()

def sprite_move(sid, nx, ny):
    s = sprites.get(sid)
    if not s: return
    sprite_clear(sid)
    s['x'] = int(nx); s['y'] = int(ny)
    sprite_draw(sid)

def sprite_del(sid):
    if sid in sprites:
        sprite_clear(sid); del sprites[sid]

# ---------------- Parser / Executor ----------------
def split_statements(line):
    """Split a line into statements using ':' but not inside quotes."""
    parts = []; cur = ""; inq = False; qch = None
    i = 0
    while i < len(line):
        ch = line[i]
        if ch in ('"', "'"):
            if inq and ch == qch:
                inq = False; qch = None
                cur += ch
            elif not inq:
                inq = True; qch = ch; cur += ch
            else:
                cur += ch
        elif ch == ':' and not inq:
            parts.append(cur.strip()); cur = ""
        else:
            cur += ch
        i += 1
    if cur.strip(): parts.append(cur.strip())
    return parts

def split_commas_preserving_quotes(s):
    out = []; cur=""; inq=False; qch=None
    for ch in s:
        if ch in ('"', "'"):
            if inq and ch == qch:
                inq=False; qch=None; cur+=ch
            elif not inq:
                inq=True; qch=ch; cur+=ch
            else:
                cur+=ch
        elif ch == ',' and not inq:
            out.append(cur.strip()); cur=""
        else:
            cur+=ch
    if cur.strip(): out.append(cur.strip())
    return out

def find_line_index(lines, target):
    try:
        return lines.index(int(target))
    except ValueError:
        basic_error("LINE NOT FOUND")

def parse_assignment(lhs, rhs):
    """Handle assignment LHS which may be array element like A(5) or variable A$."""
    lhs = lhs.strip()
    arr_match = re.match(r'^([A-Za-z_]\w*\$?)\s*\(\s*(.+)\s*\)\s*$', lhs)
    if arr_match:
        name = arr_match.group(1)
        idx_expr = arr_match.group(2)
        idx = int(safe_eval(idx_expr))
        val = safe_eval(rhs)
        if name not in arrays:
            basic_error("VARIABLE NOT DEFINED")
        arrays[name][idx] = val
    else:
        # plain variable
        name = lhs
        val = safe_eval(rhs)
        variables[name] = val

def execute_statement(stmt, lines):
    """Execute a single BASIC statement. Return False to stop program."""
    global pc_index, running_program, cursor_r, cursor_c, last_key
    if not stmt:
        return True
    # match command word if present
    m = re.match(r'^([A-Za-z\$\_][A-Za-z0-9\$\_]*)\b(.*)$', stmt.strip())
    if not m:
        # treat as expression -> evaluate and print (like direct expression)
        val = safe_eval(stmt)
        put_text(val)
        return True
    cmd = m.group(1).upper()
    args = m.group(2).strip()

    # TRACE
    if trace_mode:
        print(f"[TRACE] Executing: {cmd} {args}")

    try:
        if cmd == "PRINT":
            if args == "":
                put_text("")
            else:
                parts = split_commas_preserving_quotes(args)
                out_parts = []
                for p in parts:
                    v = safe_eval(p)
                    out_parts.append("" if v is None else str(v))
                # handle semicolon ending (no newline) if last char was ';' in original args
                if args.endswith(";"):
                    # print without newline - we'll place text and not move to next line
                    # small hack: put_text then adjust cursor to no newline
                    put_text(" ".join(out_parts), newline=False)
                else:
                    put_text(" ".join(out_parts))
        elif cmd == "LET":
            if "=" not in args:
                basic_error("SYNTAX ERROR")
            lhs, rhs = args.split("=",1)
            parse_assignment(lhs, rhs)
        elif cmd == "INPUT":
            # INPUT "Prompt";A$  or INPUT A
            if '"' in args or "'" in args:
                pm = re.match(r'["\'](.*?)["\']\s*,\s*(.+)', args)
                if pm:
                    prompt, var = pm.groups()
                    put_text(prompt)
                    v = basic_input(var.strip())
                    variables[var.strip()] = v
                else:
                    basic_error("SYNTAX ERROR")
            else:
                var = args.strip()
                v = basic_input(var)
                variables[var] = v
        elif cmd == "IF":
            mm = re.match(r'(.+)\s+THEN\s+(.+)', args, re.I)
            if not mm:
                basic_error("SYNTAX ERROR")
            cond, thenpart = mm.groups()
            if safe_eval(cond):
                if re.match(r'^\d+$', thenpart.strip()):
                    pc_index = find_line_index(lines, int(thenpart.strip())) - 1
                else:
                    for s in split_statements(thenpart):
                        execute_statement(s, lines)
        elif cmd == "GOTO":
            pc_index = find_line_index(lines, int(args)) - 1
        elif cmd == "CLS":
            cls()
        elif cmd == "LOCATE":
            parts = split_commas_preserving_quotes(args)
            if len(parts) >= 2:
                r = int(safe_eval(parts[0])); c = int(safe_eval(parts[1]))
                locate(r,c)
        elif cmd == "PSET":
            parts = split_commas_preserving_quotes(args)
            if len(parts) >= 2:
                x = safe_eval(parts[0]); y = safe_eval(parts[1])
                ch = "*" if len(parts) < 3 else safe_eval(parts[2])
                pset(x,y,ch)
        elif cmd == "PGET":
            parts = split_commas_preserving_quotes(args)
            if len(parts) >= 2:
                put_text(pget(safe_eval(parts[0]), safe_eval(parts[1])))
        elif cmd == "FOR":
            # FOR i = start TO end [STEP s]
            m2 = re.match(r'([A-Za-z_]\w*\$?)\s*=\s*(.+)\s+TO\s+(.+?)(?:\s+STEP\s+(.+))?$', args, re.I)
            if not m2:
                basic_error("FOR SYNTAX")
            var, start, end, step = m2.groups()
            variables[var] = safe_eval(start)
            stepv = safe_eval(step) if step else 1
            stack.append(("FOR", var, safe_eval(end), stepv, pc_index))
        elif cmd == "NEXT":
            var = args.strip()
            found = False
            for i in range(len(stack)-1, -1, -1):
                if stack[i][0] == "FOR" and stack[i][1] == var:
                    _, name, endv, stepv, for_line = stack[i]
                    variables[name] = variables.get(name, 0) + stepv
                    if (stepv >= 0 and variables[name] <= endv) or (stepv < 0 and variables[name] >= endv):
                        pc_index = for_line
                    else:
                        stack.pop(i)
                    found = True
                    break
            if not found:
                basic_error("NEXT WITHOUT FOR")
        elif cmd == "GOSUB":
            stack.append(("GOSUB", pc_index))
            pc_index = find_line_index(lines, int(args)) - 1
        elif cmd == "RETURN":
            found = False
            for i in range(len(stack)-1, -1, -1):
                if stack[i][0] == "GOSUB":
                    _, ret = stack.pop(i)
                    pc_index = ret
                    found = True
                    break
            if not found:
                basic_error("RETURN WITHOUT GOSUB")
        elif cmd in ("END","STOP"):
            running_program = False
            return False
        elif cmd == "REM" or cmd.startswith("'"):
            pass
        elif cmd == "RANDOMIZE":
            if args.strip().upper() == "TIMER" or args.strip()=="":
                random.seed(int(time.time()*1000) & 0xFFFFFFFF)
            else:
                random.seed(int(safe_eval(args)))
        elif cmd == "RND":
            safe_eval("RND()")
        elif cmd == "SOUND":
            parts = split_commas_preserving_quotes(args)
            if len(parts) >= 1:
                freq = int(safe_eval(parts[0]))
                dur = int(safe_eval(parts[1])) if len(parts) > 1 else 200
                basic_sound(freq, dur)
        elif cmd == "DIM":
            # DIM A(10),B$(5)
            items = split_commas_preserving_quotes(args)
            for item in items:
                m3 = re.match(r'([A-Za-z_]\w*\$?)\s*\(\s*(\d+)\s*\)', item)
                if not m3:
                    basic_error("DIM SYNTAX")
                name, size = m3.groups()
                dim_array(name, int(size))
        elif cmd == "PEEK":
            put_text(safe_eval(f"PEEK({args})"))
        elif cmd == "POKE":
            parts = split_commas_preserving_quotes(args)
            if len(parts) != 2:
                basic_error("POKE SYNTAX")
            addr = int(safe_eval(parts[0])); val = int(safe_eval(parts[1]))
            memory[addr % MEMORY_SIZE] = val
        elif cmd == "SPRITE":
            # SPRITE id CREATE x,y,"line|line"
            m3 = re.match(r'(\w+)\s+(\w+)\s*(.*)$', args)
            if not m3:
                basic_error("SPRITE SYNTAX")
            sid, sub, tail = m3.groups()
            sub = sub.upper()
            if sub == "CREATE":
                parts = split_commas_preserving_quotes(tail)
                if len(parts) < 3:
                    basic_error("SPRITE CREATE SYNTAX")
                x = int(safe_eval(parts[0])); y = int(safe_eval(parts[1]))
                patt_raw = parts[2]
                if (patt_raw.startswith('"') and patt_raw.endswith('"')) or (patt_raw.startswith("'") and patt_raw.endswith("'")):
                    txt = patt_raw[1:-1]
                    patt = txt.split("|")
                else:
                    try:
                        patt = json.loads(patt_raw.replace("'", '"'))
                    except:
                        patt = [patt_raw]
                sprite_create(sid, x, y, patt)
            elif sub == "DRAW":
                sprite_draw(sid)
            elif sub == "CLEAR":
                sprite_clear(sid)
            elif sub == "MOVE":
                parts = split_commas_preserving_quotes(tail)
                sprite_move(sid, int(safe_eval(parts[0])), int(safe_eval(parts[1])))
            elif sub == "DEL":
                sprite_del(sid)
        elif cmd == "INKEY" or cmd == "INKEY$":
            put_text(inkey$())
        elif cmd == "KEY$":
            # KEY$ prints or assigns
            if args == "":
                put_text(variables.get("KEY$", ""))
            elif "=" in args:
                left, right = args.split("=",1)
                variables[left.strip()] = safe_eval(right)
        elif cmd == "GET":
            k = get_key_blocking()
            variables["KEY$"] = k
            put_text(k)
        elif cmd == "LOADDEMO":
            load_demo(args.strip())
        elif cmd == "TRACE":
            global trace_mode
            if args.strip().upper() == "ON":
                trace_mode = True
            elif args.strip().upper() == "OFF":
                trace_mode = False
            else:
                trace_mode = not trace_mode
            put_text("TRACE " + ("ON" if trace_mode else "OFF"))
        elif cmd == "AUTO":
            # AUTO start[,step]
            global auto_mode, next_auto_line, auto_step
            if args.strip()=="":
                auto_mode = True; next_auto_line = 10; auto_step = AUTO_STEP_DEFAULT
            else:
                parts = args.split(",")
                next_auto_line = int(parts[0])
                auto_step = int(parts[1]) if len(parts)>1 else AUTO_STEP_DEFAULT
                auto_mode = True
            put_text(f"AUTO ON {next_auto_line},{auto_step}")
        elif cmd == "RENUM":
            # RENUM [step]
            step = int(args) if args.strip() else 10
            renumber_program(step)
            put_text("OK")
        elif cmd == "FILES":
            files = list_bas_files()
            for f in files:
                put_text(os.path.basename(f))
        elif cmd == "SAVE":
            fname = args.strip()
            if fname == "":
                basic_error("SAVE SYNTAX")
            save_program_text(fname)
            put_text("SAVED")
        elif cmd == "LOAD":
            fname = args.strip()
            if fname == "":
                basic_error("LOAD SYNTAX")
            load_program_text(fname)
            put_text("LOADED")
        elif cmd == "FRE":
            put_text(safe_eval(f"FRE({args or '0'})"))
        elif cmd == "TIMER" or cmd == "TIME":
            put_text(safe_eval("TIMER()") if cmd=="TIMER" else safe_eval("TIME()"))
        else:
            # Try assignment (A=...), or expression evaluation
            if "=" in stmt:
                lhs, rhs = stmt.split("=",1)
                parse_assignment(lhs, rhs)
            else:
                # evaluate and print
                val = safe_eval(stmt)
                put_text(val)
    except BasicError as e:
        # Print basic-style errors
        msg = str(e)
        put_text(msg)
        # stop program if runtime error
        running_program = False
        return False
    return True

# ---------------- Program Runner ----------------
def run_program():
    global pc_index, running_program, last_key, key_buffer
    lines = sorted(program.keys())
    pc_index = 0
    running_program = True
    try:
        while pc_index < len(lines) and running_program:
            line_no = lines[pc_index]
            code = program[line_no]
            # update KEY$
            poll_key()
            variables["KEY$"] = last_key or ""
            # split and execute
            for stmt in split_statements(code):
                cont = execute_statement(stmt, lines)
                if cont is False:
                    running_program = False
                    break
                # poll keys to keep responsive
                poll_key()
            pc_index += 1
    except BasicError as e:
        put_text(str(e))
        running_program = False
    except Exception as e:
        put_text(f"?RUNTIME ERROR: {e}")
        running_program = False

# ---------------- File IO & Demos ----------------
def save_program_text(fname):
    with open(fname, "w", encoding="utf-8") as f:
        for n in sorted(program.keys()):
            f.write(f"{n} {program[n]}\n")

def load_program_text(fname):
    global program
    program = {}
    with open(fname, "r", encoding="utf-8") as f:
        for ln in f:
            ln = ln.rstrip("\n")
            if not ln.strip(): continue
            m = re.match(r'^\s*(\d+)\s+(.*)$', ln)
            if m:
                num = int(m.group(1)); code = m.group(2)
                program[num] = code

def list_bas_files():
    os.makedirs(GAME_FOLDER, exist_ok=True)
    return sorted(glob.glob(os.path.join(GAME_FOLDER,"*.bas")))

def ensure_demo_folder():
    os.makedirs(GAME_FOLDER, exist_ok=True)
    files = list_bas_files()
    if not files:
        demo1 = [
            '10 CLS',
            '20 PRINT "NUMBER GUESS DEMO"',
            '30 RANDOMIZE TIMER',
            '40 LET N = INT(RND()*10)+1',
            '45 PRINT "GUESS 1-10"',
            '50 INPUT A',
            '60 IF A=N THEN PRINT "YOU WIN!": END',
            '70 PRINT "NOPE! TRY AGAIN!"',
            '80 GOTO 50'
        ]
        demo2 = [
            '10 CLS',
            '20 PRINT "PADDLE DEMO: A/D to move, Q to quit"',
            '30 LET P=40',
            '35 CLS',
            '40 LOCATE 1,1',
            '50 PRINT "PRESS A/D TO MOVE"',
            '60 LET K$ = KEY$',
            '70 IF K$="q" OR K$="Q" THEN END',
            '80 IF K$="a" OR K$="A" THEN LET P=P-1',
            '90 IF K$="d" OR K$="D" THEN LET P=P+1',
            '100 CLS',
            '110 LOCATE 12,1',
            '120 FOR I=1 TO 78',
            '130 IF I=P THEN PRINT "@"; ELSE PRINT ".";',
            '140 NEXT I',
            '150 PAUSE 0.05',
            '160 GOTO 60'
        ]
        with open(os.path.join(GAME_FOLDER,"guess.bas"), "w", encoding="utf-8") as f:
            f.write("\n".join(demo1))
        with open(os.path.join(GAME_FOLDER,"paddle.bas"), "w", encoding="utf-8") as f:
            f.write("\n".join(demo2))

def load_demo(name):
    path = os.path.join(GAME_FOLDER, name if name.lower().endswith(".bas") else name + ".bas")
    if not os.path.exists(path):
        for fn in list_bas_files():
            if name.lower() in os.path.basename(fn).lower():
                path = fn; break
    if os.path.exists(path):
        load_program_text(path)
    else:
        put_text("DEMO NOT FOUND")

# ---------------- Utilities: AUTO / RENUM ----------------
def renumber_program(step=10):
    global program
    lines = sorted(program.keys())
    new_prog = {}
    n = step
    for ln in lines:
        new_prog[n] = program[ln]
        n += step
    program = new_prog

# ---------------- Input (blocking) ----------------
def basic_input(varname):
    """Blocking input from user; returns numeric if possible else string."""
    if curses is None or screen_win is None:
        val = input("? ")
        try:
            return safe_eval(val)
        except:
            return val
    put_text("? ")
    curses.echo(); curses.nocbreak(); screen_win.nodelay(False)
    try:
        s = screen_win.getstr().decode('utf-8')
    except:
        s = ""
    finally:
        screen_win.nodelay(True); curses.noecho(); curses.cbreak()
    try:
        return safe_eval(s)
    except:
        return s

# ---------------- REPL / Editor ----------------
def repl_loop(stdscr=None):
    global auto_mode, next_auto_line, auto_step
    if curses and stdscr is not None:
        init_curses()
    else:
        # no curses: still okay but limited UI
        pass
    print_boot_screen()
    ensure_demo_folder()
    files = list_bas_files()
    if files:
        put_text("Found .bas files:"); put_text(", ".join([os.path.basename(f) for f in files]))
    while True:
        # read a raw line from user. With curses, temporarily switch to blocking getstr
        if curses and screen_win:
            curses.nocbreak(); curses.echo(); screen_win.nodelay(False)
            try:
                raw = screen_win.getstr().decode('utf-8')
            except:
                raw = ""
            finally:
                screen_win.nodelay(True); curses.noecho(); curses.cbreak()
        else:
            try:
                raw = input("> ")
            except EOFError:
                raw = "EXIT"
        if raw is None:
            raw = ""
        line = raw.rstrip("\n")
        if line.strip() == "":
            continue
        uline = line.strip()
        # Commands
        if uline.upper() == "RUN":
            run_program(); continue
        if uline.upper() == "LIST":
            for n in sorted(program.keys()):
                put_text(f"{n} {program[n]}")
            continue
        if uline.upper() == "NEW":
            program.clear(); variables.clear(); arrays.clear(); put_text("OK"); continue
        if uline.upper().startswith("SAVE "):
            fname = line.split(" ",1)[1].strip()
            save_program_text(fname); put_text("SAVED"); continue
        if uline.upper().startswith("LOAD "):
            fname = line.split(" ",1)[1].strip()
            if os.path.exists(fname):
                load_program_text(fname); put_text("LOADED")
            else:
                put_text("FILE NOT FOUND")
            continue
        if uline.upper().startswith("LOADDEMO "):
            load_demo(uline.split(" ",1)[1].strip()); continue
        if uline.upper() == "EXIT":
            restore_curses(); print("Goodbye."); sys.exit(0)
        if uline.upper() == "HELP":
            put_text("Commands: RUN LIST NEW SAVE <f> LOAD <f> LOADDEMO <name> AUTO RENUM TRACE FILES EXIT")
            continue
        # Line-numbered editing or immediate statement
        if re.match(r'^\d+', uline):
            parts = uline.split(None,1)
            num = int(parts[0])
            if len(parts) == 1:
                program.pop(num, None)
            else:
                program[num] = parts[1]
            continue
        # handle AUTO mode line insertion without numbering
        if auto_mode and re.match(r'^[A-Za-z]', uline):
            program[next_auto_line] = uline
            next_auto_line += auto_step
            continue
        # otherwise immediate execution
        # allow multiple statements separated by ':'
        for stmt in split_statements(uline):
            execute_statement(stmt, sorted(program.keys()))

def print_boot_screen():
    cls()
    put_text(f"*** {VERSION} ***")
    free_est = MEMORY_SIZE - len(json.dumps(program)) - 2000
    put_text(f"{free_est} BYTES FREE")
    put_text("READY.")

# ---------------- Main entry ----------------
def main():
    # initialize curses if available
    if curses:
        try:
            curses.wrapper(repl_loop)
        except KeyboardInterrupt:
            restore_curses(); print("Interrupted; exiting.")
        except Exception as e:
            restore_curses(); print("Error:", e); raise
    else:
        repl_loop()

if __name__ == "__main__":
    main()