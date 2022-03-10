#!/usr/bin/env python3

import argparse
import curses
import curses.textpad
import datetime
import json
import os
import re
import serial
import sys
import threading
import time
import socket


class CommandHistory(object):
    def __init__(self, l = []):
        self.d = { v: 1 for v in l }
        self.idx = 0

    def add(self, v):
        self.d[v] = 1
        self.idx = self.len()

    def getall(self):
        return list(self.d.keys())

    def len(self):
        return len(self.d.keys())

    def get(self, idx):
        l = self.len()
        if l == 0:
            return None
        if idx >= l:
            return None
        return self.getall()[idx]

    def getPrev(self):
        self.idx -= 1
        l = self.len()
        if self.idx < 0 or self.idx > (l - 1):
            self.idx = 0
        return(self.get(self.idx))

    def getNext(self):
        self.idx += 1
        l = self.len()
        if self.idx >= l:
            self.idx = l - 1
        return(self.get(self.idx))



class HistoryEditor(object):
    def __init__(self, **kwargs):

        self.magic_numbers = {
            10:  { 'name': 'enter', 'exit': True, },
            27:  { 'name': 'escape', 'exit': True, },
            259: { 'name': 'arrow_up', 'exit': True, },
            258: { 'name': 'arrow_down', 'exit': True, },
            339: { 'name': 'page_up', },
            338: { 'name': 'page_down', },
            564: { 'name': 'alt_arrow_up', },
            523: { 'name': 'alt_arrow_down', },
            360: { 'name': 'end', },
            262: { 'name': 'home', },
        }

        self.curses  = kwargs.pop('curses')
        self.width   = kwargs.pop('width')
        self.height  = kwargs.pop('height')
        self.topleft = kwargs.pop('topleft',(0,0))
        self.command_history = CommandHistory(kwargs.pop('commands',[]))

        self.iw = self.curses.newwin(
            self.height, self.width,
            self.topleft[0], self.topleft[1]
        )
        self.iw.scrollok(True)
        self.iw.idlok(True)

        self.ib = self.curses.textpad.Textbox(self.iw)

    def getres(self):
        return self.last_res

    def validator(self, ch):
        info = self.magic_numbers.get(ch, {'name': 'none'})
        if info.get('exit',False):
            ch = 7
  
        self.last_res = info['name']
        if self.res_cb is not None and callable(self.res_cb):
            self.res_cb(self.last_res, ch)

        return ch

    def edit(self, res_callback):
        self.res_cb = res_callback
        try:
            while True:
                m = self.ib.edit(self.validator).strip()
                if self.last_res == 'enter':
                    self.command_history.add(m)
                    return m
                elif self.last_res == 'arrow_up':
                    self.scroll_back()
                elif self.last_res == 'arrow_down':
                    self.scroll_forward()
        except Exception as e:
            raise Exception(f'Exception in input thread: {repr(e)}')

    def scroll_back(self):
        m = self.command_history.getPrev()
        self.iw.clear()
        self.iw.addstr(m if m is not None else '')
        self.iw.refresh()

    def scroll_forward(self):
        m = self.command_history.getNext()
        self.iw.clear()
        self.iw.addstr(m if m is not None else '')
        self.iw.refresh()

    def refresh(self):
        self.iw.refresh()

    def clear(self):
        self.iw.clear()


class ScrollablePad(object):
    def __init__(self, **kwargs):

        self.physical_height = kwargs.pop('physical_height')
        self.width           = kwargs.pop('width')
        self.virtual_height  = kwargs.pop('virtual_height')
        self.curses          = kwargs.pop('curses')
        self.help            = kwargs.pop('help','')
        self.topleft         = kwargs.pop('topleft',(0,0))
        self.line_offset     = 0

        self.o = None
        if self.virtual_height == 0:
            self.o = curses.newwin(
                self.physical_height, self.width,
                self.topleft[0], self.topleft[1]
            )
        else:
            self.o = curses.newpad(
                self.virtual_height, self.width
            )

        self.o.scrollok(True)
        self.o.idlok(True)

        if self.virtual_height > 0:
            self.o.addstr('\n' * self.virtual_height)

        self.o.addstr(self.help)

    def addstr(self, *args, **kwargs):
        self.o.addstr(*args, **kwargs)

    def refresh(self):
        if self.virtual_height == 0:
            self.o.refresh()
        else:
            top_line_idx = self.virtual_height - self.physical_height
            top_line_idx += self.line_offset
            if top_line_idx > (self.virtual_height - self.physical_height):
                top_line_idx = self.virtual_height - self.physical_height
            elif top_line_idx < 0:
                top_line_idx = 0

            self.o.refresh(
                top_line_idx, 0, 
                self.topleft[0], self.topleft[1],
                self.physical_height-1, self.width
            )
         
    def scrollPageUp(self):
        self.line_offset -= self.physical_height
        self.refresh()

    def scrollPageDown(self):
        self.line_offset += self.physical_height
        self.refresh()

    def scrollLineUp(self):
        self.line_offset -= 1
        self.refresh()

    def doLineDown(self):
        self.line_offset += 1
        self.refresh()

    def scrollEnd(self):
        self.line_offset = 0
        self.refresh()

    def scrollTop(self):
        self.line_offset = self.physical_height - self.virtual_height
        self.refresh()


class StreamyThing(object):
    def __init__(self, **kwargs):
        self.host = kwargs.pop('host')
        self.port = kwargs.pop('port')
        self.dev  = kwargs.pop('device')
        self.baud = kwargs.pop('baud')
        self.sk = None 
        self.sr = None 
        if self.host is not None and self.port is not None:
            self.sk = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            hp = (self.host, self.port)
            self.sk.connect(hp)
            self.skf = self.sk.makefile('rb')
        elif self.dev is not None and self.baud is not None:
            self.sr = serial.Serial(self.dev, self.baud)

        if self.sk is None and self.sr is None:
            raise Exception('Could not create stream. Must provide host/port or dev/speed')

    def paramStr(self):
        if self.sk:
            return f'Host: {self.host} Port: {self.port}'
        elif self.sr:
            return f' Port: {self.dev} Speed: {self.baud} bit/s '
        return ''
           
    def readline(self):
        if self.sr:
            return self.sr.readline()
        elif self.skf:
            return self.skf.readline()

    def write(self, b):
        if self.sr:
            self.sr.write(b)
        elif self.sk:
            self.sk.send(b)

class SplitSerial(object):
    def __init__(self, **kwargs):
        wh = os.get_terminal_size()
        self.width  = wh.columns;
        self.height = wh.lines;

        self.help = """

Commands:

    __ Log Manipulations __

    [ESC]             : Exit
    [PageUp]          : Scroll back one screen
    [PageDown]        : Scroll forward one screen
    [Alt-Arrow-Up]    : Scroll back one line
    [Alt-Arrow-Down]  : Scroll forward one line

    __ Command Manipulations __
    
    [Arrow-Up]        : Scroll back command history
    [Arrow-Dow]       : Scroll forward command history
    [Enter]           : Issue command
    [Ctrl-A]          : cursor to beginning of line 
    [Ctrl-B]          : cursor left
    [Ctrl-D]          : delete character under cursor
    [Ctrl-E]          : cursor to end of line
    [Ctrl-H]          : delete character backward
    [Ctrl-K]          : clear to end of line
    [Ctrl-L]          : refresh edit window

        """

        self.common_commands = []
        self.color_pats = {}
        self.configdata = {}

        self.running = False
        self.pad_offset = 0
        self.lcount = 0

    def getArgs(self):
        parser = argparse.ArgumentParser(description='Yet Another Serial Console Thingy')

        me0 = parser.add_mutually_exclusive_group()

        me0.add_argument(
            '--host',
            type=str,
            default=None,
            help='Name of remote host to open connection to'
        )
        me0.add_argument(
            '--device', '-d',
            type=str,
            default='/dev/ttyUSB1',
            help='Name of serial port to open'
        )

        me1 = parser.add_mutually_exclusive_group()

        me1.add_argument(
            '--baud', '-b',
            type=int,
            default=1000000,
            help='Serial port speed'
        )
        me1.add_argument(
            '--port', '-p',
            type=int,
            default=5001,
            help='remot port to open'
        )

        parser.add_argument(
            '--input-window-height', '-iwl',
            type=int,
            default=1,
            help='Size of input window in lines'
        )
        parser.add_argument(
            '--history-length', '-hl',
            type=int,
            default=1000,
            help='Length of history in lines',
        )
        parser.add_argument(
            '--logfile', '-l',
            type=str,
            default=os.path.join(os.path.expanduser('~'), 'splitserial.log'),
            help='name of logfile to write'
        )
        parser.add_argument(
            '--debug-log', '-dl',
            type=str,
            default=None,
            help='name of debug log to append to'
        )
        parser.add_argument(
            '--show-timestamp', '-t',
            action='store_true',
            help='timestamp each line received'
        )
        parser.add_argument(
            '--config', '-c',
            type=str,
            default=os.path.join(os.path.expanduser('~'),'.splitserial_config.json'),
            help='config file to load',
        )

        self.args = parser.parse_args()

 
    def loadConfig(self):
        cfile = self.args.config

        if cfile is None or not os.path.exists(cfile):
            cfile = os.path.join(os.path.dirname(__file__), 'splitserial_config.json')
            if not os.path.exists(cfile):
                cfile = None

        if cfile is not None:
             with open(cfile,'r') as ifh:
                 self.configdata = json.load(ifh);
       
        self.common_commands = self.configdata.get('common_commands',[])
        self.color_pats = self.configdata.get('color_patterns', {})


    def initFromArgs(self):
        
        # load the arguments, but favor anythign that was in the config file
        self.ilines = self.configdata.get(
            'input_window_height',
            self.args.input_window_height
        )
        self.device = self.configdata.get(
            'device',
            self.args.device
        )
        self.baud = self.configdata.get(
            'baud',
            self.args.baud
        )

        self.remote = self.configdata.get('remote',
            { 'host': self.args.host,
              'port': self.args.port 
            }
        )

        self.logfn  = self.configdata.get(
            'logfile',
            self.args.logfile
        )
        self.pad_lines = self.configdata.get(
            'history_length',
            self.args.history_length
        )
        self.timestamp = self.configdata.get(
            'show_timestamp',
            self.args.show_timestamp
        )
        self.debug_log = self.configdata.get(
            'debug_log', 
            self.args.debug_log
        )

        if self.height < 7 + self.ilines:
            raise Exception('Sorry, we\'ll need at least a few lines for the console')

        self.olines = self.height - self.ilines - 3

        self.debug_log = None
        if self.args.debug_log is not None:
            self.debug_log = open(self.args.debug_log, 'a')
            self.lprint(self.makeFileHeaderString())

    def lprint(self, *args, **kwargs):
        if self.debug_log is not None:
            print(datetime.datetime.now().isoformat() + ': ', end='', file=self.debug_log)
            print(*args, **kwargs, file=self.debug_log, flush=True)
 

    def titledRectangle(self, **kwargs):
        window = kwargs.pop('window',self.stdscr)
        title = kwargs.pop('title',None)
        topleft = kwargs.pop('topleft',(0,0))
        bottomright = kwargs.pop('bottomright', (10,10))
        boxattr = kwargs.pop('boxattr', curses.A_NORMAL)
        titleattr = kwargs.pop('titleattr', curses.A_NORMAL)

        window.attron(boxattr)
        curses.textpad.rectangle(
            window,
            topleft[0], topleft[1],
            bottomright[0], bottomright[1]
        )
        window.attroff(boxattr)

        if title is not None:
            window.attron(titleattr)
            window.addstr(topleft[0], topleft[1] + 5, title)
            window.attroff(titleattr)


    def _start(self):

        color_idx = 1
        for name, val in self.color_pats.items():
            val['idx'] = color_idx
            fg = getattr(curses, val['fg'])
            bg = getattr(curses, val['bg'])
            curses.init_pair(color_idx, fg, bg)
            color_idx += 1
 
        self.titledRectangle(
            window=self.stdscr,
            topleft=(0,0),
            bottomright=(self.olines-1, self.width-2),
            title=' ' + self.conn.paramStr() + ' ',
            boxattr=curses.A_DIM,
            titleattr=curses.A_ITALIC
        )

        self.opad = ScrollablePad(
            width=self.width-3,
            physical_height=self.olines-2,
            virtual_height=self.pad_lines,
            topleft=(1,1),
            help=self.help,
            curses=curses,
        )

        self.titledRectangle(
            window=self.stdscr,
            topleft=(self.olines, 0),
            bottomright=(self.olines+self.ilines+1, self.width-2),
            title=' Commands ',
            boxattr=curses.A_DIM,
            titleattr=curses.A_ITALIC
        )

        self.iwin = HistoryEditor(
            curses=curses,
            height=self.ilines,
            width=self.width-3,
            topleft=(self.olines+1, 1),
            commands=self.common_commands,
        )

        self.running = True
        self.start_input_thread()
        self.start_output_thread()

        self.stdscr.refresh()
        self.opad.refresh()
        self.iwin.refresh()

        while self.running:
            time.sleep(0.25)

    def issueCommand(self, m):
        self.conn.write((m + '\n').encode('utf-8',errors='ignore'))
        self.iwin.clear()
        self.iwin.refresh()

    def validator_callback(self, res, ch):
        if res == 'escape':
            self.cleanup()
        elif res == 'page_up':
            self.opad.scrollPageUp()
        elif res == 'page_down':
            self.opad.scrollPageDown()
        elif res == 'alt_arrow_up':
            self.opad.scrollLineUp()
        elif res == 'alt_arrow_down':
            self.opad.doLineDown()
        elif res == 'end':
            self.opad.scrollEnd()
        elif res == 'home':
            self.opad.scrollTop()

    def _input_thread_fn(self):

        while self.running:
             try:
                 m = self.iwin.edit(self.validator_callback)
                 self.issueCommand(m)
             except Exception as e:
                 self.lprint(f'Exception in input thread: {repr(e)}')

        self.lprint('ithread exited') 

    def start_input_thread(self):
        self.ithread = threading.Thread(target=self._input_thread_fn)
        self.ithread.daemon = True
        self.ithread.start()


    def _output_thread_fn(self):
        self.last_ts = datetime.datetime.now()

        while True:
            try:

                l = bytes(filter(lambda x: x != 0,self.conn.readline())).decode('utf-8',errors='replace')

                if len(l):
                    if self.ofh is not None:
                        header = f'{datetime.datetime.now().isoformat()}: '
                        self.ofh.write(header.encode('utf-8'))
                        self.ofh.write((l.strip() + '\n').encode('utf-8'))
                        self.ofh.flush()

                    color = None
                    for n in self.color_pats:
                        v = self.color_pats[n]
                        m = re.search(v['pattern'], l, re.IGNORECASE)
                        if m:
                            color = v['idx']
                            break

                    if self.timestamp:
                        now = datetime.datetime.now()
                        delta = (now - self.last_ts).total_seconds() + 0.05
                        dstr = re.sub(r'\.\d+$','',now.isoformat())
                        self.opad.addstr(f'{dstr}, {delta:3.1f} | ')
                        self.last_ts = now
                    
                    if color is not None:
                        self.opad.addstr(l, curses.color_pair(color))
                    else:
                        self.opad.addstr(l)
                    self.lcount += 1
                    self.opad.refresh()
            except Exception as e:
                self.lprint(f'Exception in output_thread_fn: {repr(e)}')

    def start_output_thread(self):
        self.othread = threading.Thread(target=self._output_thread_fn)
        self.othread.daemon = True
        self.othread.start()

    def makeFileHeaderString(self):
        configstr = json.dumps(self.configdata, indent=2).splitlines()
        headermsg = [
            '#',
            f'# {sys.argv[0]} log file',
            f'# Opened at {datetime.datetime.now().isoformat()}',
            '# Args:',
        ]
        headermsg += [ f'# {s}' for s in json.dumps(vars(self.args), indent=2).splitlines() ]
        headermsg += [
            '#',
            '# Configdata:'
        ]
        headermsg += [ f'# {s}' for s in configstr ]
        headermsg += [
            '#',
            '#',
        ]
        return '\n'.join(headermsg)


    def start(self):
        try:
            self.conn = StreamyThing(
                host=self.remote['host'],
                port=self.remote['port'],
                device=self.device, 
                baud=self.baud, 
            )
        except Exception as e:
            self.lprint('Could not open connection. Exiting.')
            self.lprint(e)
            sys.exit(-1)


        self.ofh = None
        if self.logfn is not None:
            try:
                self.ofh = open(self.logfn, 'ab')
                self.ofh.write(self.makeFileHeaderString().encode('utf-8'))
            except Exception as e:
                self.lprint(f'Error: could not open log file "{self.logfn}" for writing: {repr(e)}')

        self.stdscr = curses.initscr()
        curses.start_color()
        curses.noecho()
        curses.cbreak()
        self.stdscr.keypad(True)
        try:
            self._start()
        except Exception as e:
            self.lprint('exception',repr(e))
            self.cleanup()


    def cleanup(self):
        self.running = False
        curses.nocbreak()
        self.stdscr.keypad(False)
        curses.echo()
        curses.endwin()
        sys.exit(0)

if __name__ == '__main__':
    ss = SplitSerial()
    ss.getArgs()
    ss.loadConfig()
    ss.initFromArgs()
    ss.start()

