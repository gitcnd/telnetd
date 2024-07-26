# telnetd.py

__version__ = '1.0.20240726'  # Major.Minor.Patch

# Created by Chris Drake.
# Full-featured telnet daemon for micropython  https://github.com/gitcnd/telnetd

import uos
import sys
import time
import select
import socket
import gc
#import machine
#from io import IOBase 
import uio

class telnetd(uio.IOBase):

    def __init__(self):
        #print("telnetd init")
        self.server_socket = None
        self.sockets = []  # Dict of open TCP/IP client_socket connections for both input and output ['sock'] is the socket. ['addr'] is the client address. ['buf'] is the socket buffer. ['r'], ['w'], ['e'] is the state

        self._nbuf = ""
        self._line = ""
        self._cursor_pos = 0
        self._lastread = time.ticks_ms()
        self._esc_seq = ""
        self._reading_esc = False
        self._insert_mode = True  # Default to insert mode
        self._hist_loc = -1  # Start with the most recent command (has 1 added before use; 0 means last)

        self._TERM_WIDTH = 80
        self._TERM_HEIGHT = 24
        self._TERM_TYPE = ""
        self._TERM_TYPE_EX = ""
        #self._SAVE = "\0337\033[s" # Save cursor position
        #self._REST = "\033[u\0338" # Restore cursor position
        #self._YEL = "\033[33;1m" # Bright yellow
        #self._NORM = "\033[0m"   # Reset all attributes
        #self.led = machine.Pin(8, machine.Pin.OUT)
    
        self.iac_cmds = [ # These need to be sent with specific timing to tell the client not to echo locally and exit line mode
            # First set of commands from the server
            b'\xff\xfd\x18'  # IAC DO TERMINAL TYPE
            b'\xff\xfd\x20'  # IAC DO TSPEED
            b'\xff\xfd\x23'  # IAC DO XDISPLOC
            b'\xff\xfd\x27', # IAC DO NEW-ENVIRON
        
            # Second set of commands from the server
            b'\xff\xfa\x20\x01\xff\xf0'  # IAC SB TSPEED SEND IAC SE
            b'\xff\xfa\x27\x01\xff\xf0'  # IAC SB NEW-ENVIRON SEND IAC SE
            b'\xff\xfa\x18\x01\xff\xf0', # IAC SB TERMINAL TYPE SEND IAC SE
        
            # Third set of commands from the server
            b'\xff\xfb\x03'  # IAC WILL SUPPRESS GO AHEAD
            b'\xff\xfd\x01'  # IAC DO ECHO
            b'\xff\xfd\x1f'  # IAC DO NAWS
            b'\xff\xfb\x05'  # IAC WILL STATUS
            b'\xff\xfd\x06'  # IAC DO LFLOW
            b'\xff\xfb\x01'  # IAC WILL ECHO
        ]
    

    def print_console_message(self,msg):
        print(f"\0337\033[s\033[H\033[33;1m{msg}\033[0m\033[u\0338",end="") # Save cursor pos, go to top-left, yellow, show message, white, restore cursor

    def accept_telnet_connect(self,unused):
        #print("accept_telnet_connect:",self,unused)
        client_sock, client_addr = self.server_socket.accept() # client_socket['sock'] is the socket, client_socket['addr'] is the address

        self.sockets.append({
            'sock': client_sock,
            'addr': client_addr, 
            'buf': b'', 
            'r': "", 
            'w': "", 
            'e': "",
            'a': "" # unauthenticated
        })

        self.print_console_message("Telnet connection from {}".format(client_addr))
        client_sock.setblocking(False)

        # Tell the new connection to set up their terminal for us
        for i, cmd in enumerate(self.iac_cmds + [b'Password: ']):
            #print("sent: ", binascii.hexlify(cmd))
            client_sock.send(cmd)
            # Wait for the client to respond
            time.sleep(0.1)
            if i>2:
                ready_to_read, _, _ = select.select([client_sock], [], [], 5)
                if ready_to_read:
                    ignore = client_sock.recv(1024)
                    #if ignore:
                    #    print("got: ", binascii.hexlify(ignore)) #        b'fffa200033383430302c3338343030fff0fffa27000358415554484f52495459012f686f6d652f636e642f2e58617574686f72697479fff0fffa18004c494e5558fff0fffc01fffa1f01180073fff0fffb06fffd01'
                                                                 # data:  b'fffd03fffb18fffb1ffffb20fffb21fffb22fffb27fffd05fffc23'
                                                                 # data:  b'fffa200033383430302c3338343030fff0fffa27000358415554484f52495459012f686f6d652f636e642f2e58617574686f72697479fff0fffa18004c494e5558fff0'
                                                                 # data:                                                                                                                                        b'fffc01fffa1f01180073fff0fffb06fffd01'
                else:
                    self.print_console_message(f"No response from telnet client {client_addr} within timeout. Disconnected")
                    client_sock.close()
                    del self.sockets[-1]

        client_sock.setblocking(False)
        client_sock.setsockopt(socket.SOL_SOCKET, 20, uos.dupterm_notify) # keep this here; moving it up causes input weirdness


    def telnetd(self, password, port=23, ip='0.0.0.0'): # see sh2.py which calls this via:    shell.cio.telnetd(shell,cmdenv['sw'].get('port', 23)) # tell our shell to open up the listening socket
        import network

        # Create a non-blocking socket
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.setsockopt(socket.SOL_SOCKET, 20, self.accept_telnet_connect)
        self.server_socket.setblocking(False)
        self.server_socket.bind((ip, port))
        self.server_socket.listen(1)

        self.tspassword=password
        for i in (network.AP_IF, network.STA_IF):
            wlan = network.WLAN(i)
            if wlan.active() and (ip=='0.0.0.0' or ip==wlan.ifconfig()[0]):
                print("Telnet server started on {}:{}".format(wlan.ifconfig()[0], port))


    def _read_nonblocking(self): # for STDIN only
        if select.select([sys.stdin], [], [], 0)[0]:
            self._nbuf += sys.stdin.read(1)
            #self._nbuf += sys.stdin.read() # hangs
            #print(f" got={self._nbuf} ") # cnd

            i = self._nbuf.find('\n') + 1
            if i < 1: i = None
            ret = self._nbuf[:i]
            self._nbuf = self._nbuf[len(ret):]
            return ret
        return None


    def _process_input(self, char):
        self._lastread = time.ticks_ms()
        
        if self._reading_esc:
            self._esc_seq += char
            if self._esc_seq[-1] in 'ABCDEFGH~Rnc': 
                response = self._handle_esc_sequence(self._esc_seq[2:])
                self._reading_esc = False
                self._esc_seq = ""
                if response:
                    return response
            elif time.ticks_ms() - self._lastread > 100:
                self._reading_esc = False
                self._esc_seq = ""
                return self._line, "esc", self._cursor_pos
        elif char == '\x1b':  # ESC sequence
            self._reading_esc = True
            self._esc_seq = char
        elif char == '\x03':  # ctrl-C ^C
            print("KeyboardInterrupt:")
            raise KeyboardInterrupt
        elif char in ['\x7f', '\b']:  # Backspace
            if self._cursor_pos > 0:
                self._line = self._line[:self._cursor_pos - 1] + self._line[self._cursor_pos:]
                self._cursor_pos -= 1
                print('\b \b' + self._line[self._cursor_pos:] + ' ' + '\b' * (len(self._line) - self._cursor_pos + 1), end='')
        elif char in ['\r', '\n']:  # Enter
            ret_line = self._line
            """ for bash, not telnet
            err='sh: !{}: event not found'
            if ret_line.startswith("!"): # put history into buffer
                if ret_line[1:].isdigit():
                    nth = int(ret_line[1:])
                    history_line = self.get_history_line(nth)
                    if history_line:
                        self.ins_command(history_line)
                    else:
                        print(err.format(nth)) # sh: !123: event not found
                        return '' # re-show the prompt
                else:
                    pfx = ret_line[1:]
                    history_line = self.search_history(pfx,0)
                    if history_line:
                        self.ins_command(history_line)
                    else:
                        print(err.format(pfx)) # sh: !{pfx}: event not found
                        return '' # re-show the prompt
            else:
            """
            if 1:
                print('\r')
                self._line = ""
                self._cursor_pos = 0
                self._hist_loc = -1
                return ret_line, 'enter', self._cursor_pos

        elif char == '\001':  # repl exit
            return 'exit', 'enter', 0
    
            """ for bash, not telnet
            elif char == '\t':  # Tab
                #return self._line, 'tab', self._cursor_pos
                current_input = self._line[:self._cursor_pos]
                if any(char in current_input for char in [' ', '<', '>', '|']):
                    # Extract the word immediately at the cursor
                    last_space = current_input.rfind(' ') + 1
                    #if last_space == -1:
                    #    last_space = 0
                    #else:
                    #    last_space += 1
                    word = current_input[last_space:self._cursor_pos]
            
                    try:
                        for entry in uos.listdir():
                            if entry.startswith(word):
                                self.ins_command(self._line[:self._cursor_pos] + entry[len(word):] + self._line[self._cursor_pos:])
                                break
                    except OSError as e:
                        print(f"Error listing directory: {e}")
    
                else:
                    from sh1 import _iter_cmds
                    for cmd in _iter_cmds():
                        if cmd.startswith(current_input):
                             self.ins_command(self._line[:self._cursor_pos] + cmd[len(current_input):] + ' ' + self._line[self._cursor_pos:])
                             break
                    del sys.modules["sh1"]
    
            """
    
        else:
            if self._insert_mode:
                self._line = self._line[:self._cursor_pos] + char + self._line[self._cursor_pos:]
                print(f'\033[@{char}', end='')  # Print char and insert space at cursor position
            else:
                self._line = self._line[:self._cursor_pos] + char + self._line[self._cursor_pos + 1:]
                print(char, end='')
            self._cursor_pos += 1
        
        return None

    def _handle_esc_sequence(self, seq):

        if seq in ['A', 'B']:  # Up or Down arrow
            i = 1 if seq == 'A' else -1
            
            if seq == 'B' and self._hist_loc < 1:
                return
        
            self._hist_loc += i

            history_line = self.search_history(self._line[:self._cursor_pos], self._hist_loc)

            #print(f"arrow {seq} line {self._hist_loc} h={history_line}")
            
            if history_line:
                self.ins_command(history_line,mv=False)
            else:
                self._hist_loc -= i

            #return self._line, 'up' if seq == 'A' else 'down', self._cursor_pos
        elif seq == 'C':  # Right arrow
            if self._cursor_pos < len(self._line):
                self._cursor_pos += 1
                print('\033[C', end='')
        elif seq == 'D':  # Left arrow
            if self._cursor_pos > 0:
                self._cursor_pos -= 1
                print('\033[D', end='')
        elif seq == '3~':  # Delete
            if self._cursor_pos < len(self._line):
                self._line = self._line[:self._cursor_pos] + self._line[self._cursor_pos + 1:]
                print('\033[1P', end='')  # Delete character at cursor position
        elif seq == '2~':  # Insert
            self._insert_mode = not self._insert_mode
        elif seq in ['H', '1~']:  # Home
            if self._cursor_pos > 0:
                print(f'\033[{self._cursor_pos}D', end='')  # Move cursor left by current cursor_pos
            self._cursor_pos = 0
        elif seq in ['F', '4~']:  # End
            d=len(self._line) - self._cursor_pos
            if d>0:
                print(f'\033[{d}C', end='')  # Move cursor right by difference
            self._cursor_pos = len(self._line)
        elif seq == '1;5D':  # Ctrl-Left
            if self._cursor_pos > 0:
                prev_pos = self._cursor_pos
                while self._cursor_pos > 0 and self._line[self._cursor_pos - 1].isspace():
                    self._cursor_pos -= 1
                while self._cursor_pos > 0 and not self._line[self._cursor_pos - 1].isspace():
                    self._cursor_pos -= 1
                print(f'\033[{prev_pos - self._cursor_pos}D', end='')
        elif seq == '1;5C':  # Ctrl-Right
            if self._cursor_pos < len(self._line):
                prev_pos = self._cursor_pos
                while self._cursor_pos < len(self._line) and not self._line[self._cursor_pos].isspace():
                    self._cursor_pos += 1
                while self._cursor_pos < len(self._line) and self._line[self._cursor_pos].isspace():
                    self._cursor_pos += 1
                print(f'\033[{self._cursor_pos - prev_pos}C', end='')
        elif seq.endswith('R'):  # Cursor position report
            try:
                self._TERM_HEIGHT, self._TERM_WIDTH = map(int, seq[:-1].split(';'))
            except Exception as e:
                import binascii
                print("term-size set command {} error: {}; seq={}",format(seq[:-1],e,  binascii.hexlify(seq)  ))
            return self._line, 'sz', self._cursor_pos
        elif seq.startswith('>') and seq.endswith('c'):  # Extended device Attributes
            self._TERM_TYPE_EX = seq[1:-1]
            return seq, 'attr', self._cursor_pos
        elif seq.startswith('?') and seq.endswith('c'):  # Device Attributes
            self._TERM_TYPE = seq[1:-1]
            return seq, 'attr', self._cursor_pos
        return None



    def readline(self):
        #self.led.value(1)
        if self.input_content:
            line = self.input_content
            self.input_content = ""
            return line
        raise EOFError("No more input")

    def _del_old_socks(self,sockdel):
        for i in sockdel:
            client_socket=self.sockets[i]
            client_socket['sock'].close()
            p=f"Closed telnet client {i} IP {client_socket['addr']}"
            del self.sockets[i]
            self.print_console_message(p)

    def readinto(self, b):
        #self.led.value(1)
        #print("readinto b=", b)
        self.read(0) # fill _nbuf
        n = min(len(self._nbuf), len(b))
        if n == 0:
            return None
        b[:n] = self._nbuf[:n].encode('utf-8')
        self._nbuf = self._nbuf[n:]
        return n



    def read(self, n): # not needed for dupterm
        #self.led.value(1)
        #print("read", n)
        c=self.read_input()
        if c is not None:
            self._nbuf += c
        if len(self._nbuf) >= n:
            result = self._nbuf[:n]
            self._nbuf = self._nbuf[n:]
        else:
            result = self._nbuf
            self._nbuf = ""
        return result.encode('utf-8')


    def ioctl(self, op, arg):
        #self.led.value(1)
        if op == 3 and self._nbuf:
            return const(0x0001)
        return 0


    # Read input from stdin, sockets, or files
    def read_input(self):
        #self.led.value(1)

        chars=1 # keep doing this 'till we get nothing more
        if chars:
        #while chars:
            chars=''
            #chars = self._read_nonblocking() # Read from stdin

            # Read from sockets
            sockdel=[]
            for i, client_socket in enumerate(self.sockets):
                client_socket['r'], _, client_socket['e'] = select.select([client_socket['sock']], [], [client_socket['sock']], 0)
                for s in client_socket['r']:
                    if 1:#try:
                        #data = client_socket['sock'].recv(1024).decode('utf-8').rstrip('\000')
                        data = client_socket['sock'].recv(1024)
                        #if data:
                        #    print("data: ", binascii.hexlify(data)) # data:  b'0d00'
                        data = data.rstrip(b'\000') # enter-key has 00 added after it
                        if data:
                            try:
                                data = data.decode('utf-8')
                            except:
                                data='?'

                            if 'a' in client_socket: # not authenticated yet
                                client_socket['a'] += data
                                if ord(client_socket['a'][-1]) == 0x0d or len(client_socket['a'])>63: # caution; neither client_socket['a'][-1]=='\n' nor client_socket['a'].endswith('\n') work here!
                                    client_socket['a'] = client_socket['a'][:-1] # .rstrip('\n') does not work here
                                    #if client_socket['a'] == self.tspassword:
                                    if self._chkpass('chk',client_socket['a'],self.tspassword):
                                        import network
                                        del client_socket['a'] # this lets them in
                                        #client_socket['sock'].send()
                                        client_socket['buf']="\r\nWelcome to {} - {} Micropython {} on {} running {} v{}\r\n".format(network.WLAN(network.STA_IF).config('hostname'),uos.uname().sysname,uos.uname().version,uos.uname().machine,__file__,__version__).encode('utf-8')
                                        #print("",end='')
                                        self.send_chars_to_all("")
                                    else:
                                        try:
                                            client_socket['sock'].send(b'wrong.\r\n')
                                        except:
                                            pass
                                        sockdel.insert(0,i) # kick off the attempt
                            else:
                                chars = chars + data if chars else data
                        else:
                            #print("EOF ", client_socket['addr'])
                            sockdel.insert(0,i) # remember to close it shortly (backwards from end, so index numbers don't change in the middle)
                    #except Exception as e:
                    #    print("read Exception ",e, "on ", client_socket['addr'])
                    #    continue
    
                for s in client_socket['e']:
                    self.print_console_message(f"Handling exceptional condition for {client_socket['addr']}")
                    if i not in sockdel:
                        sockdel.insert(0,i) # remember to close it shortly (backwards from end, so index numbers don't change in the middle)
    
            self._del_old_socks(sockdel)
    
    
            if self.server_socket:# Accept new connections
                readable, _, exceptional = select.select([self.server_socket], [], [self.server_socket], 0)
                for s in exceptional:
                    print("server_socket err?",s)
                for s in readable:
                    # Handle new connection
                    self.accept_telnet_connect(None) # self.server_socket)

        if chars:
            return chars

            if chars: # old code below

                for char in chars:
                    response = self._process_input(char)
                    if response:
                        user_input, key, cursor = response
                        if key=='enter':
                            #if len(user_input):
                            #    self.add_hist(user_input)
                            return user_input
                        elif key != 'sz': 
                            oops=f" (mode {key} not implimented)";
                            print(oops +  '\b' * (len(oops)), end='')

            elif time.ticks_ms()-self._lastread > 100:
                time.sleep(0.1)  # Small delay to prevent high CPU usage

        return None

    def write(self, data):
        self.send_chars_to_all(data.decode('utf-8'))
        return(len(data))

    # Send characters to all sockets and files. should be called often with '' for flushing slow sockets (until it says all-gone)
    def send_chars_to_all(self, chars):
        if chars:
            chars = chars.replace('\r\n', '\n').replace('\n', '\r\n') # # Convert LF to CRLF (not breaking any existing ones)
            #if isinstance(chars, bytes):
            #    print("BAD");exit();#chars = chars.replace(b'\\n', b'\r\n')  # Convert LF to CRLF
            #else:
            #    chars = chars.replace('\\n', '\r\n')  # Convert LF to CRLF

            #chars= binascii.hexlify(chars)


            # Send to stdout
            # sys.stdout.write(chars) # not in dupterm
            # sys.stdout.flush() # AttributeError: 'FileIO' object has no attribute 'flush'

        # Flag to check if any buffer has remaining data
        any_buffer_non_empty = False

        # Send to all sockets
        sockdel=[]
        for i, client_socket in enumerate(self.sockets):
            if 'a' in client_socket:
                continue # as-yet unauthenticated connection
            client_socket['buf'] += chars.encode('utf-8')
            if client_socket['buf']:
                _, client_socket['w'], client_socket['e'] = select.select([], [client_socket['sock']], [client_socket['sock']], 0)
                for s in client_socket['w']:
                    try:
                        bsent=client_socket['sock'].send(client_socket['buf'])
                        client_socket['buf'] = client_socket['buf'][bsent:]  # Fix partial sends by updating the buffer
                    except Exception as e:
                        self.print_console_message('Telnet socket send exception: {}'.format(e)) # Socket send exception: {}
                        sockdel.insert(0,i) # remember to close it shortly

            if client_socket['buf']: # Update the flag if there is still data in the buffer
                any_buffer_non_empty = True

            if len(client_socket['buf']) > 80:
                client_socket['buf'] = client_socket['buf'][-80:]  # Keep only the last 80 chars

        self._del_old_socks(sockdel)

        return any_buffer_non_empty


    def open_socket(self, address, port, timeout=10): # GPT
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            sock.connect((address, port))
            self.sockets.append(sock)
            self.initialize_buffers()
        except Exception as e:
            print('Telnet socket setup failed: {}'.format(e))  # Socket setup failed: {}

    # Method to flush buffers
    def flush(self):
        while self.send_chars_to_all(""):
            pass # time.sleep(0.1)  # Prevent a tight loop

        
    # Test or create a shadow password
    def _chkpass(self, op, pwd, cur=None): # Caution: this must live in sh1.py (called from sh.py)
        import binascii
        import uhashlib
        if op == 'chk':
            stored_data = cur.split('$')
            if stored_data[1] != '5':
                print("bad pwd hash algo") #  Unsupported hash algorithm in existing password.  Expected linux shadow format 5 (salted sha256)
                return
            hasher = uhashlib.sha256()
            hasher.update(stored_data[2].encode() + pwd.encode()) # Hash the input password with the stored salt
            return binascii.b2a_base64(hasher.digest()).decode().strip() == stored_data[3] # check it matched the current password
        else: # hash and return new password
            salt = binascii.b2a_base64(os.urandom(32)).decode().strip()
            hasher = uhashlib.sha256()
            hasher.update(salt.encode() + pwd.encode())
            return '$5${}${}$'.format(salt, binascii.b2a_base64(hasher.digest()).decode().strip())


    def stop():
        uos.dupterm(None)
        del sys.modules['telnetd']
        for client_socket in self.sockets:
            client_socket['sock'].close()
        self.server_socket.close()
        del sys.modules['telnetd']


def start():

    t=telnetd()
    t.telnetd("$5$bl0zjwUtt8T2WLJBH5Vadl/Ix6X+cFdJr5td4a0B+n0=$1txXuyLLzAvAMM/jYSlpRScy3nSwvTQ05Mv7At5LiSs=$") # linux shadow format. default password is: pass
    # Create passwords with:  t._chkpass('','pass')
    uos.dupterm(t)


start()


# import gc
# gc.collect()
# gc.mem_free() 
# import os
# os.dupterm(None)
# import sys
# del sys.modules['telnetd']
# gc.collect()
# gc.mem_free() 
