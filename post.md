Hi all, I've created this tool because I wanted to be able to really quickly start scripts on my laptop or servers that are resistant.

What started as a 1-2 day project grew a bit larger to become rather feature complete.

Here's an animation:

https://raw.githubusercontent.com/kootenpv/sysdm/master/demo.gif

I have previously used `screen`, `systemctl` (and journalctl for watching its logs), and `supervisord`.
Even though they are very solid, it always felt like a drag having to set up a script that can easily be monitored, and restarts on crashes / file changes.

Some issues with each:

- screen has issues with keys being far from obvious, being "difficult" (to remember how) to kill screens, not being able to scroll up when I had to, ... it was inconsistent and annoying to work with.
- `supervisord` was only running on Python 2, and while usable, it is also not the most convenient for users.
- systemd (and its CLI `systemctl`) are great, but take a lot of time to set up properly. Afterwards, it was always a struggle to interact nicely with the service and also to view the logs.

Enter `sysdm`. Just `pip install sysdm`.

Listing the features (which I also do on github, please like it there!):

- Generates a systemd unit file on the fly (if you insist, you can edit it afterwards, but this should not be necessary)
- Uses current info to determine, and pin, working directory in your unit file.
- Script will start running, and also start on boot
- Script will cleverly restart on error (attempting multiple times)
- Changes to files in the directory of the same extension will cause a reload (e.g. `.py`)
- ... while taking into account `.gitignore` files
- Multiple people can look at it, too, when sharing a server.
- Find which units were created using `sysdm ls` and view their logs interactively
- CLI UI is aware of the window-size and is responsive (you'd *almost* think this is the web :D)
- The UI nicely preprocesses the log output, keeping it tiny and adding colors while showing status
- Optional: Will notify by email on failure only after final attempt
- The UI has keybindings (always shown at the top):
  - `S` To start/stop now
  - `T` to enable/disable on boot
  - `G` Live filter output using a string/regex
  - `↑` to scroll up logs
  - `↓` to scroll down logs
  - `→` to scroll right and see long log lines
  - `←` to scroll back
  - `b` to go back a screen
  - `q` to quit, but leave the service running
- Essentially this ensures you only need at most 1 terminal open (if you want to see the logs) rather than needing multiple!

https://github.com/kootenpv/sysdm

Basically it is a wrapper on top of systemctl/journalctl - because they are actually fantastic - but with a lot of added features that might remind you of supervisord/screen/htop as well.

I found myself copying unit files, making mistakes in setting the right paths, having to look up previous options and on an external server it gets even more annoying to edit.
This is not neccessary with `sysdm`, which will also automatically monitor for file changes and restart automatically.

sysdm is here to help with this.
