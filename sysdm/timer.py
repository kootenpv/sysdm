"https://wiki.archlinux.org/index.php/Systemd/Timers#As_a_cron_replacement"
"https://mjanja.ch/2015/06/replacing-cron-jobs-with-systemd-timers/"
"https://seanmcgary.com/posts/how-to-use-systemd-timers/"


Persistent=true (When activated, it triggers the service immediately if it missed the last start time (option Persistent=true), for example due to the system being powered off)

OnCalendar=*-*-* 03:00:00

we can test validity with
- systemd-analyze calendar "*-*-* 03:00:00" (daily at 3 am, replace with * to run at every)

"https://github.com/systemd/systemd/issues/6680"

Timer should add to "[Unit]"
Requires=letsencrypt-example_com.service

RandomizedDelaySec=0
AccuracySec=1min

Type=simple (long running)

Type=oneshot (running once, should be activated immediately when using a timer)


1. when choosing timer, do not enable the service (so it will only run with the timer)
2. show enabled if timer or service itself is enabled!!
   if timer is enabled, disabling the service should also disable the timer!

visualize the timers in "sysdm ls"


systemctl list-timers


OnCalendar avoids possible issues with Type=oneshot + OnRunActive etc
