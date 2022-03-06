# splitserial

Simple serial console utility in Python, with intput and output split in separate frames,
and a command history.

## Motivation

I work a lot with embedded targets that I can interact with via a serial "console".
They can generally take input as commands, and spew results as one continuous log.

The commands and log get mixed up on the screen, and there is not enough resources
on the target to allow a proper curses style screen, with a "shell" and command
history, so I wrote this to provide the same from my host.


## Use

It's pretty easy:

```sh
./splitserial -d /dev/ttyUSB0 -b 115200
```

should get you started. This is written in python, with the curses library,
which is part of the standard lib in python, so no special deps.

Other features:

* `--timestamp` - to put the timestamp at the front of every lone received
* `--logfile`   - name of file to log output to
* `--debug-log` - name of file to catch errors from `splitserial.py`
* `-hl`         - the number of lines of history to retain

There's always `--help` to find out more stuff.

### Output Window

All the output from your serial port will show up in the large, upper box.
you can use `[PageUp]` and `[PageDown]` to scroll, as well as 
`[alt-upper-arrow]`, and `[alt-down-arrow]` to scroll line by line.
The `[end]` key will take you to the very end of the log so far.

### Command Window

Everything you type will appear in the command window. Hitting `[enter]` will
send that line to the port and clear the buffer. You can use `[up-arrow]` and
`[down-arrow']` to scroll up and down through the command history.

The command history retains every command in the order it appeared, however,
duplicates are removed.

It starts with a few commands that I find useful for my work.


## Configuration

You can keep a configuration file in your home directory called
`~/.splitserial_config.json`
which will override the loading of `splitserial_config.json` in this dir.

This file can let you set some commonly used (by you) commands, as well
as patterns and colors to suit your taste.

You can also override various settings form the command line with
this file. Just be aware that that config file takes precedence over
the flags!

## Alternatives

You can see output from a serial port with `grabserial` and you can send it
with `echo "foo" > /dev/ttyUSB0`.

