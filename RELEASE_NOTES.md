The wallpaper reminder works again.

- **Fixed:** the scheduled reminder and **Test Toast Now** showed nothing in any copy installed from 0.8.1 on. The library that draws the notification was never put into QiGor's own Python, so each reminder failed quietly; the Reminder tab's log said so. It is bundled now, and a reminder you already scheduled starts working after this update without being set up again.
