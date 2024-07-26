# telnetd  (a micropython telnet server)

Full-featured telnet daemon for micropython

## How to install

1. Grab the telnetd.py file
2. Put your own password (instead of "pass") onto the 3rd last line;   `t.telnetd('pass')`
3. Upload telnetd.py to your / or /lib folder
4. To run it, **first** start your network, then `import telnetd`

This code emits ANSI terminal codes, so it's best used with a good terminal program like SecureCRT or PuTTY.

You can have as many connections at once as you like - all of them connect to the same REPL at the same time, all input and output goes to everything at once.

Connection and Disconnection etc messages show in yellow on the top line of all terminals (to hopefully not interfere with whatever else you're doing at the time in other sessions)

You can also do `t.telnetd(t._chkpass('','mypassword'), ip='192.168.1.123', port='10023')` if you only want it on one IP, or need to change the port.

If you're low on space, you can use the `telnetd124.mpy` file instead, as follows:

     import telnetd124
     telnetd124.start('mypassword') # accepts ip="0.0.0.0" and port="23" options too
