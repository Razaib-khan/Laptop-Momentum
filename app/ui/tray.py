import os
import sys
import base64
import logging

from PySide6.QtCore import Qt, QTimer, QByteArray, QProcess
from PySide6.QtGui import QAction, QIcon, QPainter, QPixmap, QFont, QColor, QPen, QImage
from PySide6.QtWidgets import (
    QMenu, QSystemTrayIcon, QApplication, QMessageBox,
    QDialog, QVBoxLayout, QTextBrowser,
)

from app.database import Database
import app.config as config
from app.autostart_manager import AutostartManager
from app.ui.dashboard import Dashboard

logger = logging.getLogger(__name__)


_RULES_TEXT = f"""\
<h2>Laptop Momentum &mdash; Rules</h2>

<h3>Streak</h3>
<ul>
  <li>Every day you are active for <b>{config.STREAK_MINIMUM_MINUTES}+ minutes</b> counts as a <em>streak day</em>.</li>
  <li>Consecutive streak days build your <b>current streak</b>.</li>
  <li>Your <b>longest streak</b> never decreases.</li>
  <li>Days with fewer than {config.STREAK_MINIMUM_MINUTES} minutes can be saved by a <b>lifeline</b>.</li>
</ul>

<h3>Points</h3>
<ul>
  <li>The first <b>{config.POINTS_THRESHOLD_MINUTES} minutes</b> of the day go toward the streak.</li>
  <li>Every minute <em>beyond</em> {config.POINTS_THRESHOLD_MINUTES} earns <b>1 point</b>.</li>
  <li>Points accumulate across the week (Mon 4 AM to next Mon 4 AM).</li>
</ul>

<h3>Lifelines</h3>
<ul>
  <li>Your <b>weekly target</b> is the number of points you aim to earn each week.</li>
  <li>For every <b>10 points over</b> the weekly target, you earn <b>1 lifeline</b>.</li>
  <li>Maximum lifelines you can hold: <b>{config.MAX_LIFELINES}</b>.</li>
  <li>A lifeline automatically saves a missed streak day when you have fewer than {config.STREAK_MINIMUM_MINUTES} active minutes.</li>
</ul>

<h3>Day &amp; Week Boundaries</h3>
<ul>
  <li>Day runs from <b>{config.DAY_BOUNDARY_HOUR}:00</b> to the next day {config.DAY_BOUNDARY_HOUR}:00.</li>
  <li>Week runs from <b>Monday {config.DAY_BOUNDARY_HOUR}:00</b> to the next Monday {config.DAY_BOUNDARY_HOUR}:00.</li>
  <li>Weekly points reset at the week boundary.</li>
</ul>

<h3>Notifications</h3>
<ul>
  <li><b>Streak Safe</b> &mdash; you hit the daily minimum.</li>
  <li><b>Now Earning Points</b> &mdash; you passed the point threshold.</li>
  <li><b>Points Earned</b> &mdash; daily points summary at day boundary.</li>
  <li><b>Lifeline Earned / Used</b> &mdash; lifeline awarded or consumed.</li>
  <li><b>Streak at Risk</b> &mdash; evening reminder if the streak might break.</li>
  <li><b>Weekly Target Reached / Summary</b> &mdash; end-of-week recap.</li>
</ul>

<h3>Streak Freeze</h3>
<ul>
  <li>Once per week you can <b>freeze</b> your streak — a missed day won't break it (but also won't advance it).</li>
  <li>Activate from the tray menu: <b>Freeze Streak This Week</b>.</li>
  <li>Frozen days are checked before lifelines are consumed.</li>
</ul>

<h3>Session Bonus</h3>
<ul>
  <li><b>30 minutes</b> of uninterrupted activity unlocks the session bonus.</li>
  <li>Every <b>2 minutes</b> of continued effort then earns <b>3 points</b> instead of 2.</li>
  <li>The bonus resets if you go idle (no input for 60 s).</li>
</ul>

<h3>Morning &amp; Random Bonuses</h3>
<ul>
  <li>Your <b>first activity</b> each day awards a mystery bonus (1–5 extra points).</li>
  <li>Every tick (10 s) has a <b>33 % chance</b> to drop a bonus point.</li>
</ul>

<h3>Activity Quality</h3>
<ul>
  <li>The app evaluates how <em>human</em> your input looks — typing + mouse movement, irregular timing, etc.</li>
  <li>High-quality activity = full credit. Automated / scripted input gets reduced or zero credit.</li>
  <li>A quality indicator (●) on the dashboard shows the current level.</li>
</ul>

<h3>Tips</h3>
<ul>
  <li>Points and streak are <em>separate</em> &mdash; you earn points even on non-streak days.</li>
  <li>The app tracks real keyboard &amp; mouse activity, not just screen-on time.</li>
  <li>Idle time (no input for 60 s) is ignored.</li>
  <li>A <b>progress bar</b> on the dashboard shows your weekly points at a glance.</li>
  <li>Long streaks unlock <b>tiers</b>: 7d → Consistent, 30d → Dedicated, 100d → Unstoppable, 365d → Legendary.</li>
</ul>

<h3>Activity Quality</h3>
<ul>
  <li>The app evaluates how <em>human</em> your input looks — typing, mouse movement, irregular timing.</li>
  <li><b>High</b> quality (≥50%) = 100% credit.</li>
  <li><b>Medium</b> quality (≥20%) = 50% credit.</li>
  <li><b>Low</b> quality (&lt;20%) = 0% credit (suspected automation).</li>
  <li>A quality indicator dot (●) on the dashboard shows green / yellow / red.</li>
</ul>

<h3>Lifelines &amp; Debt</h3>
<ul>
  <li>Every 10 points over the weekly target earns 1 lifeline.</li>
  <li>Max lifelines: 3. You can also go into debt up to <b>2 lifelines</b> (repaid from future earnings).</li>
</ul>

<h3>Bonuses</h3>
<ul>
  <li><b>Morning bonus</b> — first activity before noon each day awards 1–5 extra points.</li>
  <li><b>Random bonus</b> — every tick (10 s) has a 33% chance to drop a bonus point.</li>
  <li><b>Session bonus</b> — 30 min uninterrupted activity unlocks 3 points per 2 min instead of 1.</li>
</ul>

<h3>Daily Target &amp; Focus Sessions</h3>
<ul>
  <li>Set a <b>daily active target</b> (10–240 min) from the tray menu.</li>
  <li>Complete <b>focus sessions</b> (20 min uninterrupted) — tracked on dashboard.</li>
</ul>

<h3>Vacation Mode</h3>
<ul>
  <li>Toggle from the tray menu. Each missed day consumes a lifeline (up to 3 days).</li>
</ul>

<h3>Achievements</h3>
<ul>
  <li>Unlock achievements by reaching milestones: First Step (7d), Dedicated (30d), Early Bird, Night Owl, Marathoner (100 h), Centurion (1000 pts/week), Focus Master (50 sessions).</li>
</ul>

<h3>Dashboard</h3>
<ul>
  <li>Real-time timer (quality-discounted), weekly progress bar, trend arrow (▲/▼/→).</li>
  <li>Calendar heatmap, personal bests, lifetime total, records.</li>
  <li>Export data as CSV from the tray menu.</li>
</ul>
"""


_FAVICON_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAQAAAAEACAYAAABccqhmAACAAElEQVR42uy9Z5hkV3Uu/O59cuXUOU5P0kijLJAQiCiCsMhB5hoH"
    "Hl+cwZ/z5TpiwDlgjBO273W2MWATDRdjDEgogLI0oXOOlePJe38/TujqViuAZqZ7hvM+T89UnUq76py19orvAiJEiBAhQoQIESJE"
    "iBAhQoQIESJEiBAhQoQIESJEiBAhQoQIESJEiBAhQoQIESJEiBAhQoQIESJEiBAhQoQIESJEiBAhQoQIESJEiBAhQoQIESJEiBAh"
    "QoQIESJEiBAhQoQIESJEiBAhQoQI5wtkvxcQIUKEbXDOg5sEAAcAQs6fmEYKIEKEc4RdwhvIFqlUKsKdd94pTU1NaeVyWXZdl8Zi"
    "MRKPx2mhUEgQQgq6rg/oup5zXVe1LEt2HEeQZbnNGJsdGhqavu2225Y0Teu4rot8Pn/O1hwpgAgRngK7hbrRaMjT09PJjY0Nrd1u"
    "S4wxKkkSFQQhZllWvN1uZ2q1Wl7X9YSmaZKiKDIhJGVZVo9t2yOEkJwgCLIoigIhRACgSJKUIoQkJEmSKKXE/4NhGLxcLuvVanV2"
    "dHT0i2NjY3+9trY29YM/+IPnzCqIFECE70gEgn3nnXcK9913X8w0TSUej0uqqgrJZFIBkGm1WiOGYRQYY3FBEBRRFGVBEHLtdnvM"
    "tu0c51wmhIiCIFBBEBQAGiEkxjmPAZAlSaKEEEoppb6wE0mSIAgCCCEghIBzDlEUASC8TykFIQSUUoiiiEajgbm5OTMej/+Fqqq/"
    "4DiO8bM/+7Pn5HeIFECEixqBIM/Pz4vT09NCq9USLMsSKKWCKIpCu92ONxqNeL1eVy3LyhJC4gCSlNI0pTTNOe9xHGcQQBaAJgiC"
    "JIqiQghJAchwzlXOuUgIoQAIpZQCEAIBDXbi4HZwPPjrvs85R/frvLfyBD9QCsFzul8niiLW19exuLi4mEgk7piZmbnv/e9/P0ZH"
    "R5/17xcpgAgXFF0mNUWXnxz8bxgGpqenhfn5ebnZbMqEEFGWZUEURdEwDGV9fT1WLBZV0zQFWZZFWZZlxliWc37IcZyc4zhx13Vj"
    "hBCFEBITBKFACMkAUAHEKaUy51wBIHHOBX8H9z68S+gCoQyw+7Fu4e8W5u77gVDv9dxAyLvfN3g8eG736x3HweTkJJMk6X2ve93r"
    "fv3hhx9mb3/725/1+RD3+4KIcPFhj2AX7bpNAJAHH7hfuffe+xJrq2sS51xQFEXUNE36oz/8w/T6+sbExuZmnyzJ4sDgECcEMjio"
    "aZuCbVuSZVmabdtpx3HShBBFEARJkiSJMaZyzuO2bSuMsXCXh2d6JwghUtdaniCIgiB0r32HGd59v/t4t0ByzsNju8EY2/P1wWPd"
    "Qh6815O9b3C7+z0FQYCiKFRRlJsefPDBtOM41XNxLiMF8B2MXYIsYFuYqes64vz8QmJxcTHRaNQlx3FE5nKZEkH+2Ec/LjuuE2+1"
    "WvnSVjG3tr6erFSqqsuYJFAqEgLVssy+za3NkXqtFmOMiQARfT9Y1XU92el0pGQySa644iSXZZlwgHDOIIiUACDEkwaye4fs3ikZ"
    "Y3Bd9wm7b7dZvlvodgtw8BsEzwue043dAt/9nL2UwZM9vpfyCI7tVkzdt4PnuK4LTdMGYrFYIlIAEb5l+BcZ+djHPpaYm5vP/fqv"
    "vy9hmtZgp6OPG4aesyxLsW1L4Zwrpmkma7XqQLVay+l6R2WMi+BckiVFEgQh2I01wzBk27ZF23Yp59y/chnhnBPXdeGlsskThI8Q"
    "gmazhU6nA0mSAAJwPPE5TyYM3d9pL2Hb/dqneu4z+d12787d7/NUjz/V83f/v8e5eoJiSCaTWjweV73f9tkjUgDfAWi3WojF4/iL"
    "P/3T0f/68pdvW1tbv6nRah3jHEnbtrOGYaRt25Y4Z5QxTgghhHNO4VkD4Jx75igAgQrh7huAEApKBFCBgjHmX9DBRU32FAAAcF0X"
    "zWYT6XQa4HjS3XEvczx4r+B53Tv97seD53T/3/34blP86ZRE93vsZS3sfv1TKYjdr9nruwUQRRGapiEWixHbts/JtREpgEscwQX3"
    "nvf84vEvffE/37u5uXG7bTtxxjiAXT4uOAjnACiItyWDg4OCekJOtwV625/2dngAYIxjd3iAcwbO2RMu6ECpNBoN73Mp9UrfOAeh"
    "TxTMIIrefXz39ww/eQ/Be6a/U7el8lRC+mTCvfs9n85ieLJ17vXZhBDIstyJxWK6ZVnn5PqIFMAljh/7sZ/A+9//G/FP/vsnf3x9"
    "be2NrutKhASBMXQJMbpk2b8YCTxF4INzgNLdprUvrGH8j4P7zwWe2tQmhKDVbsOybKia6rkA3cvoQmBx7I64b69tpwAHr+mOGQTP"
    "272GJ1MU3c/tDsjtfqw7d9+9lr3eq3tNu7/f7lhG9/d1XRecc8Tj8baqquZe7/HtIFIAlzA+9alP4XWvex1e/OKXvKBY3HoL55Ao"
    "9WJ92xdYIKx8x+0nw24fffuBwIrY8Wz//51CE0bKKYdt29ANHVpMC5UG5/wJK9jLnN8rFrBbMJ7KHO9+/Mm+516Wy17v59/nnHNO"
    "CGGcc8Y5Z4wxzjlnhBCbUmoCsAE4/n2bEOJ23bYEQRA455dxznPB53DOYVkWXNdFMpmsxGIxIygeeraIFMAljNOnT+OjH/0X7dd/"
    "/X1vdBynn1IKxnxx5Nu7/LagekrgyRXAU5vThAKEBUpke8cG6A7h7BYml7lot9vIZLNgXdZIqDqeZId+uuh7t2B2v0eQEgRCq4JT"
    "ShkhhPuLZr4Q2/CFFZ7AOpRSk1JqBgILwADQEQShLcuyLopih1KqU0pNQRBMQRB0AI5/u0EprQPo+IJuybJsAnBlWbYlSbIppVY8"
    "HpdXVlY+0Gq13hy4WZRSWJYFVVWRSCRWNE0zIgsgwtPis5/9LEZHR4/ouv6iYGMPDPYQe8o6f4p3JTuew3nXrsqDBjbmP8b3FPxu"
    "gWSMoV6vo7e3F1SkngLiHPCfE5jGXTs181/H/ducUsrgCbIDwKaUOqIoGr7AGsEfAF0QhCaANqXUEARBp5TalFJbEARDEIQOIcRw"
    "XdcWBKGpqmpLkiRTEAQzFovZsVjMlCTJkmXZEUXR9gXbkmXZ8Y85mUzGTSaTLBaLcUVRmP+DhD/KU7lEpVIJ+Xxe3NraWg+EP1Bg"
    "nU4HiUSCq6q6vrGxYcXj8XNyjUQK4BLF9q5JbjBNazw89gyKP/e+SHlXvICFroIX+Os2i4PbACEcngwzFuy2hBDuJRmYSwVqSZJk"
    "MsYsSqkhiZJDBeISEJcz5vg7aZtS2qSUmqIoGpIktRVFsQRBsARBaIuiqAuCYBBCDEJImzHWJIR0JEnqyLJsiqJoCoJgMsZMQRCs"
    "eDxu53I5u1AouH19fSyfz/N4PA5BEEIL4Ml/g/OLer2OeDwuwitBDo8zxmCaJgYHBy1ZlldjsRgiBRDhKfF7v/dHeOCBR6V3vvN/"
    "Ppe5UDy5Z2AACO/arQnxo/RdL/YE13djwQghLgCXEMIohUsIcUSBmgBxBYG6giDYhFCLUmpQQnQQ0pEksenvsjVJlDuUUk4IdQRR"
    "sABYAAxJlurxeLyeTqdbx09c1kolk7YWU11Fkpksy1YikTDT6bQhy7IBwKGUOtls1kmn0zwej3NVVV14Anve++YvBFZXV1GpVNKd"
    "Tudod9AxiAGkUimDUroaj8cxNDR0Tj4zUgCXKKYmJ1HcKuWbjeY1jHm+PaFoqoqyIAiCC05tgQoWFYhDCTUlSWwLAm0JotAWZdFU"
    "FMURKLUAmKqq1nxz2CCUdCghHVEU24Ig2rFYzI0n4g4l1HJd12LMtSRJdjKZjJVIJp1jx47aN998M4tpscB86DaJt/0FXPwC/GzA"
    "OceXv/xliKLY47ruQPdx13Xhui56e3tboiiWujMOzxaRArgEYZombrvtNTh5hToGYCRIrglUuuu1r33tLw8ODhqyrDrZbNZOJ5Nu"
    "IhW3M5mckcmkzdHRYcf3XYFtk/iS2GEPMhqNBh577DFceeWVJxhjPcFxQggsywqKgLYkSVpvt9vn7HMjBXAJolwu48tf/iJkUTpi"
    "GEaOEgoOF5IkTv3RH/3hQ//yLx9lb3vbd+/3MiN0wTRN/ORP/iT5j//4j2v9bsbwMdu2EYvFkEqlNkzTrJ+rKkDAL/WMcGmhVquB"
    "c05s1xm3HUvhYAAH1zRtixDCrrnm6v1eYoRdsCwLpVIp1ul0ju5OZxqGgUQiAUppiTF2zmoAgMgCuCTxla98BeVyKWZZxklCEJTC"
    "6alUcgYALrvssv1eYoRdKJfLYIwlOp3OYJD67E4BDg4OglJaKRQKrmma5+xzIwVwCWJubg7F4la+VCpeFuwkgkCr6XRqIZPJRr78"
    "AcTq6ipkWY4DSAfHAkvAsiyk02nIslyxbZtrmnbOPjdyAS4xcO6V1zLGexjjvcFFJEni1pEjhzdvv/279nuJEfZAsVhEo9GIua4b"
    "6+5KZIzBtm1kMhkHwJZpmudUgUcK4BLDl7/8ZXzyk5/E7OzMUdu28oBXlCMIwvJVV11dfcELXrDfS4ywB9rtNnRdzzHGkt0xAMdx"
    "QAhBPB6vcc6nz2UGAIgUwCWJxcVF1Gr1Y4ZhKMExTdNmf/iHf7gdmf8HD5xzNJtNWJbVxxiLB8cC89+v/CsBWHmy5qVvF5ECuMRw"
    "1ZVXgXNOJVHq48wv/eXcURR1jhDiptPpZ/8hEc4pFhYWcN9994ExNkQIUYDtNmDTNBGLxSDL8ppt2+Vz/dmRArjEcPfX78E9X783"
    "22p2jnIGgHNQIpiarK4AwI033rjfS4ywC/Pz8/jVX/1VEcAxn348tAAMw0AulwOldJ1z3pZl+Zx+dqQALiFwznHXXXfh61//eu/6"
    "+vr4dgZAqOXzhaWbb3o+xsfH93uZEXZheXkZjzzyiOa67sTuAKBlWcjn81ySpAVd181z7cJFCuASw0MPPQTbtgZd18kCnikpiuJG"
    "IhHfSKfTUQrwAMI0TTiOk2GMDe0uAnIcB+l02mKMzTHGmCRJ5/SzIwVwKcHg+NKX/xMzM9OX67qRDvroBVGYG5sYr/X29+33CiPs"
    "QhfnwQCltNB93HVdMMaQTqdbhJC5eDyOc1kFCEQK4NKCCHDOhUqlesiyTMnfSTildPYDH3i/cceb37rfK4ywC6urq9jY2IDruuOc"
    "81TAqgx4PQCiKEJV1Yrrumucc8RisXP6+ZECuIRw6vRpAFAkWRoMjhFCjGQydYoQwm591cv2e4kRdmF+fh6/9mu/Bs75mOu6Svdj"
    "pmkimUxCUZRVSZIq3XRm5wpRKfAlhH/+l39C4UuF/NLi0hUeYxbAGKtpqjYvUhmSeG79xwjPHs1mE4888oh47733jsObzhRaALqu"
    "o6+vD5IkrVmW1TpXVODdiCyASwScc6ysrmKruJWrVMq5IJgkimI5k02t33DD9VEA8ABC13UsLCxoAQlIdxbAtm0kk0lQSldbrda5"
    "6wHuQqQALhE0mg2srqyAEjoiimKqi7p76cRlJ8ovfvGL9nuJEfZAq9VCu93OMsbGd/MAMsbQ09PjOo6zWSqV3N7e3nP++ZECuESw"
    "vrKOL335v7CysjphWba2XQMgzr7nl36xec311+73EiPsgUajAdM085TSnh2DTTjgOg4SiYQlCMLWyMgIznUREBApgEsIBJxzwTSt"
    "MdO0BEGgoJQwURSnc9kMs8zzYkFGeJZot9uwbXsIQKb7uO3YEAURsVhMd133nNKAdSNSAJcIGs06AMiWbfV3FZO0CcGsABGMOfu9"
    "xAi7EPj5juMMc8617olLjuNAi8egaVqFMbZ+rgaB7EakAC4R3HPvvfjrv/4/mZXllUNdh8vJVGr58NEjePvb377fS4ywCzMzM/il"
    "X/olwjk/DEDojgGYpolEIgFBEDZFUSypqnpegrhRGvASwdraOuLxeLJWq+Vd1w3GYK0PDw8VA1bZCAcLjz76KB588EGFcz6+ewRa"
    "R+9gaHgYkiyvcsabgiCclzVEFsAlguXlZRi6nuOcJ7uagBaPHj3SyOdy+728CHugXC5D1/U0gOEdff4EMC0LyVQStmPP9PX36aqq"
    "npc1RArgEgDnHJ/73Odw6vSZEcM00/7sPEYInf79P/h948jhI/u9xAi7wDmHrutgjPUyxvrCBiAALmNwHAepVMqmhM7OLy3wWq12"
    "XtYRKYBLALquo16volqpjNqWpfoXkyEI9AwhhF119VX7vcQIu9BqtbC+vg7G2ASAPIBw9iJzXYiSBDUW63RMfVE3TEQuQIQnxUc/"
    "+lGsra1KtmNfDhKe04Ysy4s9hT6cuPLEfi8xwi5sbW3ht37rt+C67ihnLIYuC0A3DAh+ExAIXaeCgJGRkfOyjkgBXAL46le/gve+"
    "99cT5XLpCGc8oJOqqLK6HldjuOLEFfu9xAi7sLCwgEqlIpqmeYRziMGYdXDAdhxks1kQQkqEClU8g4nO3y4iBXCRw8slu4jFYjnG"
    "WC8IAQdAKV3WVKWSzWb2e4kR9kCpVMLdd9+tuq47EoxUBzwGZ8eykIjHIVC64VhWm7nnr4YjUgAXORYXF/HYY4+jXK6OM4YegIIQ"
    "AQx89id/7iebr3j1K/Z7iRH2gG3b0HU9RQgZ4QAI9XZ5zjgM3UAmmYIsigv9vQU9ETt3g0B2I1IAFzlarRYeffRhzM8vjNq2laCU"
    "gBC4kiRN3fHW72bvete79nuJEXaBc452u416vZ5njPUGx4I/nwbMJSBLuUzOjqnnlgSkG5ECuMgxNTUFzjllzJ1gjMk+DVhH02Kz"
    "ADA8PLzfS4ywC8ViEdVqFZZlDQHIAtscAK7rgnMORVF0x3EW77nnnvNaxBWVh13k+PrX78L8/Fy8Wq1eDhDCOSCItCQIwlIsFken"
    "c36aSCJ8+zh16hRKpRLS6fQwIUQDPAVAKYXrupBlGbFYrEEIWYzFYshkMudtLZEFcBHDmxxjY3OzmLAsa5hz+BNl6WpPT8/mtdde"
    "v99LjLAHenp68Lu/+7uEMXaUc75jEw5IQGRZrnDOt4Ky7vOFyAK4iPH444+j2eyAECEFIMs5A0BBCVkaGxtuWFbUAnwQYRgGHnzw"
    "QcVxnBEAYQ8AYwy6rqNQKEAQhE3HcWrnm8UpsgAuYjz00EP43Oc+h0ceeeSoaZr94AAH44IgzPzt3/6tEYvF93uJEfbA0tISlpaW"
    "0o7jjDHGdjxmmibS6TREUVxJJpPtVCp1XtcSKYCLGLfeeiuKxQ3oemfCdVnC6yhjOufsFCGEUxoZeAcNnHOsr6+j0+kUdvQA+FaA"
    "bduIx+NwXXdudnbWzp3nRq5IAVzE+OY3H0SxWJZlWbmKc078irGaZVnT2WweH/zgb+73EiPsgbm5ORiGMcoYywfDW4L0HwDE43GT"
    "MTadTCaRzWbP61oiBXAR49FHHsVf//X/yVWr1SvAAXAOxniRUmFTlmUkEuf34onwrYNzjr/4i7+AYRjjlNJEdxuw4zoQJQmxWKzN"
    "OV+z7PMfw4kUwEWMarUC13GSYDzrFQAziAJdEgShERGAHExsbW2h2WxSx3EOd2cAgoyOpMjglJRNy9rcwRFwnhApgIsUnHM89MCD"
    "aLeaQ5zzbHCxUErnvus1r9YvvzzqADyIeOSRR3DvvfcqjuOMuq4bzv8DticBiZK0rmhaOZk+vwFAIFIAFy0Mw8B/f+3LmJ6ZmdD1"
    "TtqnlHIIIfN/9id/6r761bft9xIj7IHNzU0sLy+nHceZCI4FAUDTNJHJZiBK4pKqyE3xAkxyihTARYpqtQrOOWk2G6OmZcl+HtmU"
    "RGkVAG644Yb9XmKEXQhYgEzT7CWE9AY8gIA3CMS2LSSTKbiOuzI2Om7tThGeD0QK4CLFV7/6VczMTMcc170M3Av/E0IqsiwtxJQY"
    "XvCCF+z3EiPsguu6WF5ehmVZ467rZgGEVX6esBNommZxzuf+/bOfZIqiPJuPe0aIFMBFiq997Wv4u7//+8zm5sZlwRgpEJQlWdnK"
    "9xSiOYAHEMViEe9///th2/YI51wNRoEzxuC6LiRJhKqquuu4S5l0FkfGx8/7miIFcBEiaCc1dCOt63omMCNFQSwWCvnmsWPH93uJ"
    "EfZAvV4H51zweQDDDEBQABSLxaEoSkMQhfVkIgHhAmRyIgVwEWJubg6PPvooms3mIQISlooRQtZeddsr27e/5tX7vcQIe6BWq2F2"
    "dla2bXuwuwIQ8DIAWkwD56xoGEbRsqwLYsVFCuAixMLCAh5++GHMz88f0XU9FgSTVFWp/PzP/7xzOKIBP5BoNBpYWFhIGYbxBIZP"
    "y7KgqRo4x7LLWeM80gDuQKQALkJkMhlwzgVK6bjruoJfTspkWVkghLBWvbHfS4ywBxYXF1EsFvOc84Hdj7mui3QmDVEQZoeHx/Rs"
    "+sJUcUYK4CLEo48+ik9/+tOZZrN9OfemAoMKtC3L8lRvTz8Gh4b2e4kR9sDMzAx0XR93Xben+zjjHJwA8XjcIcDcvffcxYb6+y/I"
    "miIFcBFienoGZ85M5svl8mhwjIBUMpnM6rGjR/Hil754v5cYYRc455ibm4Nt22Oc81jQAORlABwQQqAoimE7zmoylkBfX98FWVek"
    "AC4ycM4xNTUFwzAGCCH5oFhEluXN0dHR0oW6cCJ8a2i32/jXf/1XGIZxmHO+Y8yP67KA96/BmbsmSeIFS+NGHSMXIT7+8Y8BIIdb"
    "rVaaUgpwQJKk+SuuvLwxNzu/38uLsAc2NzeRzWZl0zR3+P+EEDi2g0QiBVlWKpzxknwBSoADRBbARYpWqzXqOI4MeFaBKIpzP/dz"
    "P6dfdfWV+720CHtgdXUVp06dijPGnhAAtCwLyUQS4KShKvF2IpG+YOuKFMBFhuXlFXDOZUVRRr1RUhyEEFOS5FlCCHv5y2/f7yVG"
    "2ANnz57F/Px8wnXdfOD7BzUAAQsQB0rJZLydL1y4ce6RC3CR4e/+7u+Rz+dzxWLxcu8CIgDQzuYyy7Ko4MiR8zNEMsKzw9bWFpLJ"
    "ZMxxnDiAHT6+yxhUVQMBtjLZjGmZ1gVbV2QBXETgnGNy8iyWlhbzxWKxPwgAUkEox+PxpRMnTkQ9AAcQnHP4vf95QkgiOE4ICfkA"
    "YrE4KBWWD42P26IkX7C1RQrgIkK73cZ//deXYdv2IQAZQjwaQEkU14eHhkvXXnvtfi8xwh5YXFzE5uYmTNPsZ4zFAWDbDWCQRBGy"
    "LNuM8ZU//pOPIKaqF2xtkQK4iLC5uYnV1WXMzy9c2el0wp1EkqTFO9741sarXvbK/V5ihD1w6tQp/Omf/ikcxxkKugABgIPDNC3E"
    "43HIsmQC2BoY6Ecqnbxga4sUwEUE/7oRKRWGXZcJQTGJrMqzL3v1y6xXvCKaBHwQUSqVcN9994mu6x5hjIlAMBCcwLQtxBJxuK5T"
    "F0W6lkolEIudv2GguxEpgIsEnHM89tijmJqajrVa7QHGWODvG6qqTAJAbuDCRY8jPHM0m02cOnVK5ZyP7OgCJH4KMJmA67olWZKL"
    "onDhioCAKAtwUeHhhx/F7OxcYWFh4VhwIQmCUKaUzqqqBsPQ93uJEfaA4zjodDoZAGNB5yYhHgsQYwyqooJSuhRPJGq6fmHPYWQB"
    "XCQwTQeVShmu6/a5rtvj25AghGyOjo5tvOxlL9vvJUbYA/fffz/a7TaazWYf57wfQDgIJPhLplIQBGHp8suO6tnM+WcC7kakAC4S"
    "PPjgg/jCF76A5eXlcddx0iBeGkkUhYUrr7yyduJERAN+EEEpxerqKjqdzrDrutluok+PBkyCJIouIWRR1TRncPDCdAGG69vvHyjC"
    "M8PznvdczMxMYWNj/ahpmgqlFBwciqLM/Oqv/kpbli9c7jjCM8fa2ho2NzdBCBnmnCvBrg94FYCSJIFQqlNK5z/04T9DOp25oOuL"
    "FMBFBI8ERPACgAAIiCVJ8gwhhE1MHNrv5UXYA0NDQ/j4xz9OAExgh7x5RUCapgHgTRCyOjBwYXd/IAoCXjT44he/jJGREa3T6Qx4"
    "BUAEnLGOINDFWCyB5z3vefu9xAh7YG5uDqdPn1Zd193B0sLBYVkW+vr6wDmvyrK4lUolL3glZ6QALhLcffedSKfThbW1tYlgkowo"
    "iiVZlheGh4dwxRVX7PcSI+yBhYUFqKqaJYSMd8/6IyBwHAeJRAIAtlRZrWmKdsHXFymAiwTFYgmCIMYtywqbSSgla4TQkiyf/wES"
    "Eb49bGxsIJvN5h3H6aV02wNgnMFxHGiaBs75Um9vT3M/1hfFAC4C6Hob//mf/4WV1dUBXdfTjuOCMw5REOde9apXta677vr9XmKE"
    "PcA5R6lUAoBhzvkOlk/mMgiC4McAMD8xccjq77/wbE6RArgI0G4D09NnMHn27GCno8e9RhLOCaHz73vfe63v/u637/cSI+yBzc1N"
    "fO5zn4NlWUMAYsB2G7DrOpAkCYIgOIIgLPzZn/8pTk1NXfA1RgrgIsDXv/7fwWDJfs645NOAG/FEfIYQghe+8Ln7vcQIe2BmZgab"
    "m5vUtu2jAOTu4h/LthGLxcAYazuus0apiMHRKAsQYQ/8+79/AqdOPaLWarWTnEPgnIFSUo/FtEVBkBGPJ579h0Q455icnMTa2poM"
    "YLQ7/08phWVayGQyAFBUFW25p68Xg9kL7wJECuAigGXZWF/fTDmOexjwA4AC3cpkMutXXnllRAJyQLG6ugpZlpOu647vfoxzhnQ6"
    "DUEQVrOZTMll7r6sMXIBDjhOnz6NarWGarU+BpBxL/pPIVBhtlDIF6+44vL9XmKEPRCwAHHOeznnQ4GSDohAbMdBLBYD53wpl881"
    "ZVnZF0UeKYADjunpGXzhC1/E6dOnD+kdPe8RgQKc89k//OPfao+ORhyABxG2bWNrawuu645TSrMAENRvuK6XxVFVlVNCli87dtwi"
    "XTUCFxKRAjjgyGYL4NyC6/KC67oiADDOHIEKU335Eba6urrfS4ywBx5++GH88z//MyzLGnZdVyGEIGgF9vL/KmRZthj43M/8r59n"
    "fjzggiNSAAccpdImOOeiqiiXARB8F6DFOJ/X1CS+67tu2+8lRtgDjUYD1WpV4Jwfd11XCoKAgQUgesM/DAKyetUVJ9Hb27sv64wU"
    "wAHHmTNn8YEP/GaiUqkcBYJeclbUNG1pYGAAb33rHfu9xAh7oNVq4fOf/7xm2/ZosPMH8FiAkuCc1wVRWNNiGvbLAoiyAAccjXob"
    "qqqkGGN9AZMM51hKZ5KlTkePMgAHFJVKBZIkZVzXHQ/p2wkBBwFzGBLxBCgRShS0KFJp385jZAEcYHDOcdddd2J5eXmYMdYXXCSC"
    "SOdOnDjeKlzACTIRvjXMzs6iXC7nXNfNA9ssQASA7ThQVQ2c8VVJVBqqfOGbgAJECuAAgzHg63d/FadPn5rQ9U7OpwFzKaXzf/d3"
    "f2ddffVV+73ECE+CxcVFtFqtQQBZQog3v4l7PIAAgaqq4Jwv33TTTcbwyPC+rTNSAAcYZ84s+L4jGWOMK4QSEEJ0SZKmCCGIaMAP"
    "Jjj3ev1N0wx7ALwxjhyMc8iKDE3TGCFk7nu/9wfcQ4f2L5UbKYADjH/4h4/gIx/5iNZut6+APwSQcd5QVXW5UOjF7bdHg0APIhYX"
    "F/HRj34UpmkeY4xJjDFwcHACuMyFqqoQBMGglC6/5CW3IJm8sESg3YiCgAcYCwsLaDQa6U6nfTRIIQmUFgWBbqjq/lSORXh6nDp1"
    "CrOzs7LruqM7HiCArhtIxJNgjDUIIavxeHxfz2NkARxQzM3NodVqAyA9AHoABKmkaVEUS7lc9tm8fYTziKWlJSwsLGQEQTi0W7gt"
    "20IsHocgCBtaTFvt2af8f4BIARxQ1Ot1fPazn8Ps7OwRy7LywYVEqTD9yCMPd77/+79vv5cY4UmwtbWFVqvV47puH9A9CpyAM45k"
    "MgnbcVZVLV7NZPc3kxMpgAMK27YAuGg2G2OWbakAwDl3KKULBAJ+5md+dr+XGGEPcM5RLBbBGBthjGW624BdzmC7Ljyzny7l8wNt"
    "WbpwcwD3QqQADijOnDkLw9BlAJdxxkUAIIR0CCErHPvTOhrh6VGv1/Hggw/CNM0CY0ztJgFhjEGUJMiKwgG++K53/U/Httr7ut5I"
    "ARxQzMzM4Y8++MepSrl6zDvCQSkpFgr5xfGxI/u9vAhPAl3Xcffdd4MxNsg5l7pLgF3HBQEBJcQkwOJb3nwHYrH9JXSNFMABhWU4"
    "MA074bo8711DBBy8osWUWk9vfr+XF+FJcObMGVSrVcW27aOccwHYrgK0TRsxVQOltMU5lpOJBI4ePbqv643SgAcUU9NTGBoaynHO"
    "M8ExQshmT0+hZZrWfi8vwpNgY2MDX/3qV5PNZvPIjjkAfhdgKpUGIaQKgi1BEJDP768yjyyAA4rPfOZzePzxxw51Op1CcCwej2/c"
    "9urv0icmDu/38iLsAc45DMNAs9lMO47zBII/x3WRSMThuu4mgCrH/pCAdCNSAAcQnHM4bge6rg+4rqt6ZBJALpcr/fAPvdO55ppr"
    "93uJEfaAbduYn59HsVjsB1DotgCC8mC/B2Axl8+1kqnkfi85UgAHEV/+8tfBOSdUoBOcM/8cEUeSxHVCCHvhC5+/30uMsAdmZmZw"
    "5swZNJvNEdd1091FQJxzCAKFoiiggrD6qpe/0urvHdzvJUcK4CDi05/+BH7pl345Uy6VTvotAABgxGOJZQDo6enZ7yVG2AP5fB4f"
    "//jH4TjOMcbYjnntrutCEESIomhRQuZf+V2vYvn8/ldzRgrgAKLVasEwjBRjrD+IIAuC0Eql02s3XH8TcrmIB+AgotPpoFQqyZ1O"
    "5whjDIyxMAPgOA7i8RgopbogCisve+mtOH58/9O5URbggIFzjpe//BUwjL6M47rJwIyUZXkjm82tgSNqAjqgmJ2dheM4Sdd1RwP/"
    "P/jftm0kU2kIglDhLltOJ/ff/wciC+DAYW1tDV/60n9icXFx3DTNXMgCJNDpm266sXTd9dft9xIjPAkeeughrK6u9jLGBgMasKCL"
    "07ZtqIoKzvm6IAgb8UTiQCjySAEcMKRSXm+4YzsZ5roKZwwEBMlEMsYc59BrX/s6+f/+9T/tIJmMsP/gnGNqagqdTmfQtu1QcXMQ"
    "gFAwxqF5g0CWE4l4o7en8Cw/8dwgUgAHDJ/97OfAORckSTpOAJkQAkoIyuXySz74wT/8x3f9+I9+6POf//T//N//6xdv/r9//X+H"
    "isVijHMudDedRNgf/OVf/iUajcYYYyzBGAPjHJwDjHFwEMTjcQBYfsktzzOGh4f2e7kAohjAgcM999yDmZmZTKVSeQ5ACKUUhFC4"
    "LotVq9VrarXa1TMzs29/8MEHNnK57NmPf+LjZ+OJ5PTw8MjC6Ojw9Be+8P9WX/nKV5hTUzM4fnx/y0y/k9BoNMA5J+95z3vGOefe"
    "IBAEo8BdUEohyzIjlC7+zT98lKf3iQZ8NyIFcIDAOcc73/lDKJfLeV3XxwAv4Ed8LnAQCoAT13Xi9bpxuNFoHF5aXnoFFcQOIbSh"
    "qspsMpl89Fd+5VcfYpxNvupVty2++90/Ub3ttlebAFjwfhHOPb7xjW/gmmuukRzHGQr8fs45KCVwHAeKooAQYnKXrVi2heGh8f1e"
    "MoBIARwo3HPPPbjvvvtw4sRlhxljfYAfRML2WGkvuMQhCILXYupyibl2GoSkXccZabdaLwKHTiktb21unf2Jn/jJ04nELz5+/Pjx"
    "s0NDgwt/8ZGPlH7one80K9UKz+eipqJzhampKWxsbMRM0xzrPs45h2maSHhBvxYD25RlBUeOjH67H3VOESmAA4SNjQ089tijGBwc"
    "uMJ2nDBPxAEQ4vmSAAEhFP6GHu7oAfU04yDgPMYYi5mGMWIR8tJOp9Pc2twqSpI4FY8nHv+zD//Zo4l4YuqNr3njwo/98I9W7/zi"
    "Xe57P/Te/f76FzV8FqC4ZVk927EYbw6A408CBlDVVK2kyAqiGECEJ+Caa64B51x4wxveMAHOd1rrXfn/vYJ9Hns4vH/811FCAUAA"
    "RwZAxrGdI5Vy+eWU0qYoCOX5hfmZ++7/xmQsFnvsxbe85HQqnVx+zeteW/mf//MHTdu2uSzLiPDMUK/XYRiG5jhOYvvEeefJcRwk"
    "EgmIoliMp5J113EOjCsWKYADhDvvvBOnTp3K12r1y1w//Qd0Cbwv5N7dwArgAGiXJdD9jhzY2XFGRFGUOed5l7E85/wYpfRVrVar"
    "febsmS1BEM6cPn3mwT/43T84lc3np7/7jv+xfPPzb6q9613vcj7xyX/Hm9/wxv3+iQ4kOOf40R/9UTiOk+WcJ3ZwAPrZGb8JaDOX"
    "ybQ77c5+LzlEpAAOEB5//HH09BQKGxvro17Qj4Qy3NVXFt7qvtCeKXb3qDPGKCEkSSlNMsYmGo3GrQDq1Vp1Y2FhfvquO++c/ODv"
    "/9EjjLHJifGJlR/58R9p/NzP/pyz8/O/s/Ff//VfKJVKyOVyfYSQOOD/zoSDMwZZlqGqKgBUx0ZG7aXlpf1ecohIARwQcM7x+te/"
    "Hqqq9jDGU4xzCE/7qm9dAIPoNAktiVARgBBCRFFUXddVAfQx173a5dx1HbfFONsE4Y988A8/+Mgff+iPT/X29S7cfvvt62Pjo7WX"
    "3vpS6867vsY/+Hsf2u+fcV/wwAMPoFKpIJfLDXDO5dAaA4HLGCRJAqUUlNLS+Pioo+vGfi85RKQADghM08SnPvUpqIp61DSstO+/"
    "eyDAt8cdQZ5wj7MgReUfIwSMcRBCfeuAg9Ltz6aUCpzzNCU0zcGPMZe9hjFeX1la2VxeXJ55+KFHzn7hP754VpSkyRMnLl9/05ve"
    "VHzf+37dwndQ2jGRSOCv/uqvyG//9m9PEEKk7sccx4GqqlAUxZZleYUQwhqN5n4vOUSkAA4ImMvAOSevvf0NE47tymRHkSZ/is2e"
    "PKluIF3/AgDh3q4EDvCu9+vOJOyOG+xwGbwMhMo5VwkR+jj4lbZl27Zlt4hAS5TS1b/8y7+a+tu//bv1wcGhhYGB/ukf//GfWH7O"
    "c26svP3tbzMEQXC7P+9SgWma+Ld/+7eE67qX+b8avPPi9QBks1lQSnVNVRZ/53d/H6L49LbdhUKkAA4ImrUmtJgmUEq/5SbxZypO"
    "nHhK4FyBeJAJITkGnnNd9xil9CWmabqzszP6wsJ8RdPU2f/+76+c+eu//qvpfL4wed1118599atf3XjhC1/YAnBJKITl5WUoipLl"
    "nI957hVFcFYYY0gkEgBQp4Kw0t/fB03bv3HguxEpgAOCqekZ9Pb3ioyxzF7pvm9HSMLM4DnE3ilIz0IJXAdCiEApTQBItDv6aKvV"
    "flGpXNIFOlN6+OGHVv7xH/9xqr9/YDqfz51OJJPTv/3bv7vx7ne/u6Gq8kUZXNzc3ERfX1+eMZYPYiyev+XNAlAUBZzziizLpYPS"
    "BRggUgAHBJVaDVPTc6JuGMmglLQbT7VxP9XlxLuew5/B8791eA0vBASc+8VJIOH6BQJAECiAOGcs3m61x/RO5+ZqpWpTShuxWGzr"
    "gW98c/JfP/qvj+dy2ceuv+66Ux/72MfXX/6KW5vpVPrAKwTOOV75yldiYGBgjHO+i6nFO4/JZBKc861EPFHXVLbfS96BSAEcEFx7"
    "7bUYGR0gz33uc8n8/DzabW9iTDgTkJAn7OiBoiBdt7uxQ2kEE2qeVpa+FWELKhO9123HHLpjCNuPg3OIggB/qTIBCu1Wq9BqNi8X"
    "BOE1G+vr1anJqcWPf+LfTv/B7//BmVQydTqXy8389m/97tqP/cSPNP7iI3/Gfuanfu5AKYRyuYyvfe1rOHTo0DBjTPOat7zv6rgO"
    "RFGEIAiQJGnpuutu7CwfoBQgECmAAwHOOeYXVrC2tpV//RteP5pKp/GVr3wFi4uLaNTrcFwHhBPAbwwKBb9LEAgh2JHb242ux54+"
    "DPBMBYw8yf3ude1aw45jOzIOImOsx7KsHsuyrm81myYhpKIoytqDDz449bd/8zenEonEo9+858HTP/ljP1n8yf/v3Z1DRyf2PYbw"
    "4IMPQtd18o53vOMwISRsyyaEgjEXkiSBEAJRFBdveM51zoMP3Ldva90LB0eVfgej0+lgcnYRqUT89o5u/CNz3VS90cDa6irOTp7F"
    "mdNnsDA/j62tLTQajeCCAuD3AISl53xb0PcQCs4Olvn5VCD+l2LhmolDCKqc8yVVVR/NZXOn1Zg6NXFoYu7aa68rvvyVL69cddVJ"
    "ey9L6HziV37lVyCKojYzM/P3lNI3eWsnIJSi0zGQy+VwzTXXWIlk4p2L8wt/9573/MJ+/7Q7f+f9XkAEQDcMqIoilKr1X9MN83+b"
    "lkUt04TjugDn0A0D5a0iJs+exeTkJCYnJ7G2toZmsxkSTwpU2GEdAAAH3xH1Z4xdNCecEL7ju/iFSsF35LZtm6IolkVRXFcUZXH8"
    "0PhDfX29D0uydIYQUnzve9/bmp6e5rfeeut5Xec73/lOqKra32w2P0MpvQFAaAHUG00cPXoUY2NjjWwu+91nz5z9/K/96i/v90+7"
    "A5ELsI8IIuqEEHz0o/9yMp0rfFff4BDNZLOIJxJwHAeWZUFSZCiyjPm5Odx000249dZbsbKygoWFBczOzmJ5eRmlUgmW5Y0MEwRh"
    "Wwmc49TfhQTZw+XxfzMiSZJKCBlyHHvIcZzry6Xy7ZZl1qlAlwVBOPVDP/RDDyiKcvqnfuqn5k+ePFl+/vOf3zp+/Pg5Dyr6CjjH"
    "Od8xCCTIAqiqClEUq8lkcu3okf1nAX7Cb7zfC/hOQnCBtNu6vLq6lrQdO++4zlHHdsYef+yxW+eWll4DURTzhTyGh4cxMjyCXC4H"
    "TdMwPz2Dj/zZn6PQ04NDh8aRSCQRTyQAztFsNLC0tISzZ89ibn4epVIR3Q0ntKup6GI54eQZai3ut0H29/chkYx7zZCEcMaYJUnS"
    "liAIy4SQmXQ6/ZimaWdEUZzUNG3z+77v+1pTU1P8+77v+77tNZZKJfzwD/8w+vr6Xt5ut/+VEJLx1u7FYxqNFm688Uak0+lvXHnl"
    "lW/kjK0+//nP2++fdufvvN8LuJQRCHyz1RRrtXrMMs2hdrt9uWnZVzuOe4JzPmzZzqhl2xnbthXdMIStagWNZgPNZhOSKCKdSmNo"
    "YBDrK8u45977kEqlkE6nIUkyYrEYUskUkvEY4vE4REmCYRpYWl7G7OwsZqansbq8glqtBsdxIFIBguBVoW2XAHdXASIsB+acg3YH"
    "GYPvtOt/YKeV0X1BUb+J6ekzD0/EkysAEn6KF+7w0pA9vT3IZJLhAgKLwa/B54QQg3NeEQRhQRCE05TSBxhjj/b398+n0+n629/+"
    "dvO66677lsqX77zzTtx+++2444473qHr+p8RQjwqMELBOdDRdTzvec9DMpn4+Etf/MIfaHf09lVXXXUer7hv43fe7wVcKugy/8RO"
    "p6MYlh43TbtX1/VjjuNcadv21YyxY47jDukdI2GapmhZFoggQhBFjzracWC5DhzHgWEaaLfbqJaraDUaoJwhlkiAUgGdTge6bsB2"
    "HHDOIRGCRCKBRDKJeDKBZDIJSZLgOi42NzewuLiI2ekZb27dVtFzFfiOwp3d3yb4UtsKYucjT7gd4MIqgO1223w+j2w+HcY+A+Hv"
    "VgTbNF2UEUIMxlgRwJIoipOJROIxWZZnEonE3PDwcP3mm29uvuQlLzHgVSvyvX6nv/mbv8H3f//303e+853vMwzjPZRS4r8/HNdj"
    "bXruc5+LeDz2Bz/w/d/386dOnXJPnjx5nq/Ebw1RDODbRCDwhq5LhmVmq7Vqr+O6hy3TGmecjXKOccexR2zbHrMsK1uv16Vms4lK"
    "pYpqtRY25WRyOYyMjqGvrw+MM1RrdbTabciyjGQsgd58DxzTBOEcLnNh2g50XYeu67AsC6Zpod1ooFaroVKrQVIkxGNxZDIZxBMJ"
    "9PUP4JrrroNERayurWJ2dhaPP/oYpqemsbG5gVarBe4yT0BoVy5/VzT92wkjcPJt9jBh74rDAE9IfwJhEdJe79GtKPzbFECMUjoG"
    "YIwQ8oJOp2O02+1yo9FY2draKj7yyCNL//AP/zA/Pj5eGhkZWc7n8wuPP/54+YorrmgA4IQQtFot/PM//7PGGDvCOSdBoBIAHNtG"
    "LBYDpdQhhM687NZXu3/8od87Pxfjs0CkAJ4hguCT67qSZVuJWqPWZ1vOFQ5j1wC4mnM+7DhOP3PdZKvVkqu1mlSrVlEql1Gv1WCY"
    "JlrNJvL5PAYHhtDb24tUKgXdtKCoKjKZNJLJJEZGOJrNFqq1GmrVKtqtFhihcBwLlFEIogRVUaBpGmzbhmlaSMZj0A0DlmWho+uo"
    "Vquo1WpQNA3pdAaDQ0OIJRI4NDGBw4eP4KUveSkq5TIWFhZw+vRpnD17FgsLC6hUKl5Qi7HQVQAhT2om7tWk2F2s9Oxij9+a2eDR"
    "pQVLJrseY4ErEJ7LLmsAnHNCCNEopcOMsWHLskApdR3HsarVqnnq1KlGKpXaiMfjs7Is393T03P2S1/60sLNN99c/djHPpZ2XXci"
    "sDRCBeA6SKVS4Ix3BCrMvuY1r8bx48fPw5X57BC5AE+CotmBSAmRuaQ4ppl0HbvHZe5RxtwrGOMnKCHHHcYmLMvJdAxdqFYq2Nra"
    "wtbWFkqlEgBA0zRks1kUCgUUCgWYpol2uw1mexRR+XwBLmdotTswTROHJyaQy+UgSiIIpbBMC3q7g2a9jkajjkazAdM04bgMjj97"
    "zjRNMNeF47qwbRutVguWbcMwDHQMA4qq4rvvuAPpVNp7rW17f5YN4nertdotrK2uYXpmGo8/9hhmp6extbUFwzDA/eq9p/OLu4X9"
    "QlxU3cLGOUcymURvXwGE4glxjW5XYK9jYfVe13t3t0QHfAmUUkiSZGqaVo7FYsuiKC6nUqnqysrKmznnYRMXpRT1RgtXXXUV+vr6"
    "FtPp9G22ZZ95xzu+/YDj+UJkAfhwHAeCQIll2artOCmrY09AoIcMbh/jLrsMjI3atjNq23au0WiolUqFlCplbPpCb5kW4ok4NE2D"
    "KIo4ND6O45ddhkKhEO44juOZ70vzC3jsscc8Zl9CYJgWjh8/jnqtDseyocY0CKIIURSRjMeQz2TgchftdgvlcgW1eh2NVhu6rkMQ"
    "BDiOg2AYpawovmtgIm5ZqDcauPuee3DkyBEU8gXkMhkIggC9bfgpRheyqiGTzeP4icvxylfdhq2tDcxMTeH06dOYnJzE8tIy9E4H"
    "rusCeKKAANvmtr+jnncl8ISyZ869ugeQJ+zwu5/XlU7csfbd47z3Uhicc8U0zUHTNAcZY88tlUqMECLsSL1yhDRgjLGybdsV27Ev"
    "0JX8Lf6O+72A/UBwwhljAmMs4bpuxnXdcc7ZCddl14IIRxjn46Zt5yzT0uq1qlwqFsnq6irW1tbQarVQq9UQTyRweGIC2WwWI6Mj"
    "6O3phaIqaLc7KBWLKJfLEEQRMU1DtVqFruuQFRnJRBKapiEWi4ETinqj4fn17Q7isRhEWUKr04Fj2ejNFzA2OopEMgYtpgHwdiPT"
    "slCp1lCr11Gr1WCaJizLgu04oUJwOQ8VlCiKSCdTGBwYwNDQEPr7B5BOpSErCkzDgGlZcF0Xtm0B3CsuMg0T9XodKyvLOPX4KZw+"
    "dQqLiwuoViowLQsiFbYFLOAS4F2sQ8Hv/STn4dlcfN2CzTlHPB7fYQHs/gtes4NFuetvt5Ww+7W736Pbpeg+Hnx33bDw/Oc/H4lE"
    "4lN9fQPfY1lm+61vOXicit9RFoDjOKCUCp1OJ0sImeCcX8k5v5pSepQx97BtOwPtdju2WSzTjc1NrK6tY2trC51WE67jIJfLYWxs"
    "DNmsZ+3pnQ5isVgoXMlEAoRSyKKMTDqNiYkJ1Ot1LC0tYXp6GoIg4OTJkxga8iihFUWBaTuwHQe64UX9FxbmkUpnUK6UMToyAs4Z"
    "NjY2kGhrkBUFguCdskKhgNGRYQwNDUE3dFSrNZQrFdTrdTSbTbiMwXFdDPQPor9vAM1mE51WC7Ozc5ianoEkyejp6fHqDUZHkfWD"
    "hgCHbnhBRkWg6FVV5AsFnLzyKhiGjtWVZUxNTePUqccxOzODrY1NmKYF13UgCAJo1w4clCQHzUrnE0FF5BOIVH3stgSeKbothicp"
    "StrxvGAtoigEcxwWX/faVxuPPnbqvH7/bxeXrAXAHAeEUjiuIzLGY4QgSalwxHXdawHc7DjO5YZhDHU6nXixWJRWV73KutW1dbQ7"
    "OmRVQ7CHPe85z8H4+Bg0TUMmk4EkSZBlGbZloeL7/rVaDbFYDLlcDtlsFpIkoVqtolKpoNFooN3pwLIs5HM5OK4LQgiazSYarTYy"
    "2SzyhQJSiQRUVUO700an04GqqqiWyqiUypBkAZQCrXYH8XgChw8fRiKRQDzlBQ9lWQZjDJZto16vo1ytoFypodVsw7btwC6F7ccH"
    "qvU62u02DMOAJEkoFHowPDyEoeEhFHrziGsxcHjRbKOj+1WGHsklZwyWbaG4WcTC/Bwef/wUpiYnsby8jHarDddTtE8QlN1CeS4t"
    "AEVR0D/YC0HYucsHz+tez+77T/UXvE/35+62GHYft2wbiUQK11xzjStJ0s/86I/80B81GnWkUun9Fosn4JJQADbncAAoYALnXGWc"
    "ZV2HDYNjACCjkiRd5jjuhK53jldrlf6tzS1leXkZ8/Pzfk19C5lMGvlCAf39/Th2/DIMDA5BEEWUy2WUNjdDbrdsNgtVVcMAn+t4"
    "O59pWShubWF1dRXFYhGLi4uIx+M4ftllGBoagqooaLfbEAQBsXgcrVYLs7OzODs1jZ7eXoyPj0NVVSQTCbiMoVKuoN1pQ293UK/W"
    "QCkHIRwu4+jvH4AsyxBFEVo8gWQqBcd1wRnD6NiYpwzA4TguGo0WKuUyqpUKWq2WFzT0FQWhBKZpodlsotVqwTAMgACZbBaDgwMY"
    "HRtFX28vUsmUN4WIuaEycF3HazFmXnqyUatjaXEJZ06fwfT0NOZmZ/3yZBOUCk+ZSdgTT1o8sJN8BPAUgCzL6B/sgyh6bDxeMV4g"
    "qPCPPfnfkykEAHu6DbsVQLdboOs6hoZHcfTYsVYiHv/eM2fPfvK3f/MDB6qN+Wl//4OOVluHokiiaZpxUNIvCMJRQskhQvgE4eQo"
    "5zhkmXa+VColVlfXteXlZTo9PYXNrVWYpgVFUTE0NIRMOoN6vYFDhyZw/PhxKIqCfD6PdNrT1oQSOJa3q66urqJYKoExhkwmg5GR"
    "kYDvHfV6HcViMYyeS5IUPhYoC0opOp0O6vU6dF0H4PXLa5oGVVXRbrfRarWwsrKC3r5eDA4MIpvLQaAUAiUwTR2McRiGgXK5jJXV"
    "VSiqCtP2+s57e3tx7NgxKIoCSZKgxTTE4wkIggDDNNGo11EuV1CpVNBut9HptMMmm6DvoNnqoNFswzQNuMxFKpXA4OAAhoeH0d/f"
    "71k3ogTbsaDrHbiOA9MwAe4JA3M5Op0ONjc3MD09jVOPP4656Wmsr62j0+nsMKHDgOGuNuadGQUCHhYmAZx4zw9IUwP3QpIkDAz2"
    "gwoUhHR/RiDA9GkFf69swV5t14Gg760YRDRbLVx2+QmMjI6u5fL5N5RKxW+8+0d/NFIA3w6C/Ltt27JpmknHcbKMsWGADhNKrwTB"
    "ZVQgY6Io9lOBxgmFIhAq1Gt18k//9C945OFHYRgW8vk8+vp7cfjwGEZHx9Df349UKgVZUqHrepjCsywLmUwGg4MDyGZznhD7EXbH"
    "cWDbNuqNBjY3N1EqldDpdFAsFpHL5TA0NIRcLhdQQEHTNDDGsLW1heXlZUxOTsI0TZw4cQJHjhxBJpNBo9FEvd5Ab28vKKUol8t4"
    "7LHHUCwWcWh8HL19fV6MIZWAYRio1WqoNxpgjMHw11qrN0ApRT6fRywWQyKR8ASL0lAZHTp0KBhQCdd14RUlVbz38xUS556FYdle"
    "ObBh6Gi1G2i1vK7DWCyGnp4eDA4OYnBwENlsBnEtBse2YdsODMOE47hgjINSgDEXjm2jWvJqDh599FHMTE9jfmEB9Xodju1AED3r"
    "QKCC517gmZEgh1WM/jUiiqJvAYgIqBE8gQwISeiOysduAe52E/ba2fdyAZ78T0Cr3cb1z30OcrncowNDg68zdX3he+64Y79FaU8c"
    "OAXgj02izWZTM0wjyRif4JyPuK57lBByglI6RggZo4KYEUQpJgoCJdQru6SCAEoJKCHY3NzCb3zgN7GwsIixsXHcfPPNuP7669Db"
    "V4Aoil5el1CIouyVzfpCMTMzg/vvvx+u6+Lw4cMYHh7G0OAgMpk0GPM43oh/wTQaDczPz+Pee++F4zg4ceIERkdHkU6noes6XNdF"
    "pVJBuVyGYRiQZRnptJeP13UdyWQSuVwhfF69XgfzeeRTqRRisRhM04vEb26so1wu4fhll6G3txfxZAJUFCAIIuq1BmKxmB+xX8HS"
    "0hLS6TTanQ4SiQSGhoYwOjoadKZB8QuJNE2D4zjodDool8sol8uo1epotw1wcK+6jnA4jg3TMNBstWDoBgzDgCCK6OvtxeDQEEZG"
    "RtDX2wtV08BcDsuy4bo2TNOAbVugHkkYHNdBs9nEyvIKTp8+jVOnHsfU1BSq1Sps0wLt2onBPOvryYKHlNLtLIOf7hsY7IekyB4f"
    "L9m9MwczFXf2CXTffzLTfi9T/8myCYRQmJaNF9xyC9SY9sWJiUN3iIJQu/UlL9lv0doT+6IAuk4q5YwL9WZHNixdajdb/ZZljVNK"
    "DgO4gTM2KAjCuCDQHKVCXBAEVRAooZSCihKoKEISRBDijWEWBAGUUP/i5Zibm0e5VAbnwDe+8U109DaGhgZw4sQJZDIZ2JY3o63V"
    "aqHZbAEAYrEYCoUCkskkXNfF4uIiWs0mEskk8vk84vE46vU6qtUqWq0WHMeBpmnI5XIQBAGlUgmGYWBjYwOWZeHw4cMYGBhAPB73"
    "aw0EJBIJtNttrK+vY2ZmDtPT0+jr68Pll1+OoaEhaJqGVqsFxhiSySRM08TG+hpOnXoctUYDE0cOQ1ZkxFMpZLNZ1Cs11Ko1r8jI"
    "r+LLZrOoVCoAgGQqBU1VkUgmw5PebLUQi8UwOjoa1i4QALpholqtoVKuoN6oodPpwLatsN6Ac8C2HbTbbe9P70CSZWQyKQwODWN0"
    "ZBSFfA+SqQQIBQxdh2NaMC0rTE8KlMJ1XbTbbVQqFZw9cwaTk5OYnpwKeQ5E/zzSXRwHwWVLKQkj/h73HkX/YB8URfHv42l2arKn"
    "BfBUcYBn8ucyDkEQcfPNN0NR1f/74he/6Ecs07SuPHnFfoja0+KCKIDAjAcg27aTrtcbg7pp9DcazTHHtocZY0MAspTSCQCjhJCY"
    "KIqyKIqgxAviiH5hDCEexyQRBBAqQhAFiL6PHFSscbK9KxBQ30dvYGFhHo+fegyLi4sQBREAwcTEYRw/fhwDA/1hek8UPRonwzBg"
    "mgZWVlbx4IMPolgsQlVV1Ot1XHfddRgfH0dPTw9s2w6Za2RZRrVaxeOPP47JyUn09fVhbGwMg4OD4XjvdruNYrGIdrsNx3GRzxcg"
    "yzIajQZs20YikQitiFqtBsMwQAmgaSokRYEaj6Fj6Gh22lhdXkGz2sDRo0fR09MTEFACANrtNmKxGBqNRuiGSJLkFQnF4+jp6cHQ"
    "0BAEQQhjCLFYDIoaAyGArut+FsNTeHpHh217bhD83a7d6aDVbqNjtGBaNlzHU1pDQ0MYGR3CwEA/Usk0JFGEbdvQDR2O48B1XbiW"
    "Dc44BFEEc12UiiXMz81hcnISpx57BIuLC2i1WrBtOzyf1GdA2p3Wo5Sib6DfVwCBC4BnKMDUf+72/57F8EQ34KmDgASW7SKdzuD6"
    "66+HLMu/8kPv/MH3TU9P4+jRo/sk4k+N86IAOOfQdR2apon1erOn2WyO6roxbhj6dY7rHjUM44jLWAGUJAmIKlIqUkohCEJIZiFJ"
    "EkRBBIF3MkRJ8H9039wXJRD/+SKlEAiFKNLQPA+sAADgbNsMtB0L1WoNM9MzaLXaOH36NGKxOE6ePImJiXG0Wm24rotGo4F6vQ6/"
    "LhzZbBbZbNarotN1bG5uAgCSySQKBc+ML5VKaLVa0HUdqqoilUpBVVVYloVSqQRd17G4uIhcLodjx46ht7cXrsvDCrt0Oo1Wq4XV"
    "1VVMTU1haWkJIyMjuPzyyzHYPwBZkbFVKoERIJVJw7AtrK2sYnF2DtVqFRMTE0in01AUBbFYDM1mE9VqFaZpwrZtUEo918AnHJVl"
    "z/2Jx+OhtaHrXlHQ0aNHkc1mQQhCpVGv1VGrejGIRrMJy7LhuAwuY7CZCddlMA3LDzB2AMJCRTM+No7+gf5wfZxz6G0vNeo4Dlzb"
    "geArSM4Y9HYLy0vLOHPGyypMTU1ha2vLq34knvAF10qgHPr6+qBpSsAJgG5LoFt4nyj82ym8nUKOHfd3Pkb3OEbQ1g2MDI/i5MmT"
    "BiHk+ze3Nv/1Va94BW666cb9lvU9cU4UAOccmxtbSKaS0urq2oBpmuOWZV1pmuZVXgusM8ZclmaMJzkhntsuevXulFJIggAhDMBQ"
    "iKLgkynSMDAjijQM6IiiACrKIFQMd3/vOSKosL2mAIwFnWAAOMB8GmvXZVhZWcEjjzyKublZOI4dCsRVV12F8fFxiKKIs5OTKPQU"
    "YFk22s0mrrjiCtRqNUxOTuLMmTMQRRGtVguFQgHXXnst+vr6QgHUdT3sA9ja2sJDDz2EUqmE8fFxDA0NIZvNQRBEOI7nHwdKRBAE"
    "DAwMwHGc0NWIx+PI5HNodzoolktodToQCEEqkUQ6lYIgeK3CrVYLm5ubKJfLmJiYCP1/27Yhy3K4A1uWhWKxiPX1dTj+yGrGGPKF"
    "AoaGhsA5RzabRTKZRCwWQ0zTQOCZ7612B7V6HdVaHfVmE51O0yMvhQBCKCzTgGF2wniHZVlQVRW5fB5Dg4MYHBpET08v4rEYAM/a"
    "MA0DzHE968C2PQEjgKEbqFTKmJ6extnTZzB55ixWVlfRaHr8iAQEgihgoL8fqqqCEG8DoHSbN4B2CTHQbe5vK4Cdwr1Nq/hMXQFK"
    "KVqdDo5fdjmOHTmyKUnS6xzHue/t3/M2xPzvedDwrBVAs9nE448/jlQqldnaKr6l2WrfwRk/zjkrAFBFSfIrxLwfGpRAkERQQQDx"
    "d32JdisAj/AyYFMVBG/n9wo8ACp47oAgyqBE9FJkgvfjC6LolYLiiYUnIbkkJ6FC8J5DfBehFpqcMzMzaDQauPbaa3D06DFA8HK7"
    "GxsbaLda3m7l+/KDg4PQNA26rqNcLqNYLCIejyOX8zIIpmmiWq2iXq/DdV0oioJUKgVJktBqtVCvN6DrXsxgeHgYfX196O3thaIo"
    "YTNOIpFAs9nE6uoqZhfmsbi0hNGxUVx24gT6e/ugyDLaba/gR1EUMMZQLBYxNzeH9fV1DA8Po1AoeHUGySQMwwjjGEGWIB6PQxRF"
    "NJtNxBMJSJIIRVEhSxIkWQY4h6HrSCaSGB0bh6woIFSAy4B2p4NarYxms4l6tQHDMGE7JjhnoJR4bcyGGSqndrsNVVWRzqQxMjqK"
    "kZERz31JJEC4V7Fp6rpnuThevQHxrw3LMNButjA3N4fTZ85gcmoKs7MzaDabSKfTSCYSfjyIdqUcAYE+mRB7dQN7+/9P7kY8WbCw"
    "1dHxnBtvxEBf35lMKnM7Y2zubW97637L+flTAK1WC/F4XLzrrrvetb6+8R6HsR5KKKggQJb9qaiEQqACKBVBBQpQ6qV/BAGiIECk"
    "nhnfbQEIghi6BN0KQBAAKlDIkgpKRO9ki76lIAqe+YfdzSjcF3pPAQS94V5UP1AG2+ZisVjE6dOnMT09jWqtBi0RAzgwMTGBw4cP"
    "o5DLIZlI+jGJ7Ui1YRhYXl7GY489hoWFBT/N5/nnR44cQV9fHwBPaUqShGQyiU7HwMrKCh5++GFYloWJiQkMDQ0hHo9DkiQYhhGm"
    "7BrNBkzLwvDICDiAer0OwTfrg/bgoBXYsixomoZkMglVVUNLol6vY21tDYODgxgYGPDNfK8OwDRNOI6DWCyGWq2GtdVV1Op1JBIJ"
    "NBoNZFIpjAyPQJBEqFocqXQaWiyBRCKJmOalGFvNNur1Bur1Kmr1KtptL5gZuDnMdcPW5VanDd0wIAgCkskkBvsHMDI8jN7eXmTT"
    "XsGVrnf8rILrpWEtC4y5XrCXeHGOjc1NTE1PY25mGlsbG6hUKrAsIzw/gkBBCZ4guN0KYO8dHaFwdwv5XnUAwf1WR8dLb70V2VT6"
    "zkw6+ybXdYtvfvPr91vOz58C+PrXvw4AfZlM5mOGYd6yvLYGwzBB/Ki8KIqeABMBAhVBKAEVPAEnordri6AQfUGnvgUgiMHuLngn"
    "kFJQ6udqBUAWFQjUsxKoSEEFTwFQQkCwkxzCE3jmVcMy0nUMcF3mP8ZDk88jx6BotppYXV3D7MIcHNvG/Nw8jhw5gisvvwK5XC6M"
    "spumiY2NDei6F+DKZDIYGBiAJEmo1WrY2NgA5xyZTCbciS3LwlaxiFKpjE6nA1EQkUwmocU01OsNGIYO27KxsbGB3t5eDAwMIJ3N"
    "QNU0dDodyLIMTdNCt2FlZQXT09Po7e3FyZMn0dfXB1mWYZrezhuLxSBJEiqVClZWVrCysoJUKoXh4WEoigJVVcMqtlKphGazCcuy"
    "QIg32cayLMiiiJimQpJVCJIMUZIgKypcl0Og3G8wyoBSAVQgsCwD5XIJtVodjUYDnU47DOi5LgMDh2VbsEwLnU4b7WYLlFIkEgn0"
    "9w1gaGi4qx5DgeO4fimzF4x0HDuM+YAQ2KaOzfV1nDp1ClubG1hYmA8/F9xr51UUxbMPfauC7nIBugW92wJ4sgKibgXAOIPtMrzq"
    "tlcjEYv/46GRQ+9sdVr6q151fpmJnw2edTPQ8vIyDMNwr7nmGuPYsWMYGBwKO9Ba7TZc1582SzkABoEIPquTt0tTzgHqs8f4f4xw"
    "UMLBifeabQTFH56jzwkDCAXAQcDCfHNwUnYywgRVZd3gvpb33jfwi6uNOjq6Dtt1ICoirr3+OsRUDT09PThz+gzOPH4KMU0L3Y5D"
    "hw5haGgI+XweyaRnGXgXuYtCoYCRkRE0Gg2srKxgcnISlVoNm1ubODRxCGNj48hms4ipGuqNBjgHxicmYNs2VhaXwt0/l8tBpAIU"
    "SQZTWZilaDSbYf3ADTfcAEVR0Gg0YBgGUqkU4vE4ZFkO6wyC+v9CoYCEzzzcbnuBz7W1Nbiui6GhIQwPDyMWi8F1XQiCEO7Arut6"
    "xUPrG2AMoFRAvd5AMp1Avd6AKEpIp1MeI1E8jkKhFz09fWDMRaPhfZdWq4VGow7bdkAJhSIqiMfiyGXysG0b7U4bswsLmJqbg6J4"
    "TUsjI6MYHBzwUrSZDADP4nIcB4ZheM1IkoRytYK23sEVV12F59x4o2fxrKxgaXkeGxsbaLXa4PDWLfgKXwi5Bf32YR4Qj+1iReqm"
    "XA+uLeplnVzO4bgukqk0NEXlhPP5599yo3nffffvt4w/JZ61AtA0DV/84herV1999b85rnN1KpXqSSaTZGhwEMVSCWvrG9ANA8DO"
    "dkzuN6d4Yhj+4jtKwPmuUdXd2Fk4uj0II6gq7e7eCnjad/d4M8ZgWRZqtSoqlSpKpRI2t7ZgOTYkRUYsEfcq0zigqSoG+vsxfts4"
    "Os0WZqanPZ/Wz+f39/dD07SwqMj1G34YY5BlOfTt250OlldX0LPVA8MyUa6UvVSmIPgBOjckFWlUa4jH42H2YW5uDiAEakzD6uqq"
    "F4dIJpFOpzE+Pg5JkmBZFkRRhGEYqFQqWF1dDWsSgsBjKpXyUnK6DlmWofh9CpTSsCJSVdXwPAVKxLK8CH+tVkOj3oIsK4jF4ojH"
    "44jH4r6ScCEIFKZphv0KnPOw8jKTyYTEJdVqFY2GR4DqOi4sankl1JqGNHNh+AQqq2trWFxaghaLIZfNoq+vD6Ojo+jt6UUykfBr"
    "LGx02k3Mzs3hkUcfRblcRqFQQF9fHw4fPYrLr7wcekfHVnEL8/MLWF1d9VKMjgMCMYw9eRWUZMc11j16LWAh9q4h/4L1C4xchyGb"
    "yYIQYgqCMPuud/80+5mffvf+SvjT4Fm7AL/zO7+Dm2++Ga1WK97X1/e6VDr7/YV8/iYqCCnOOdq6gVq9jvX19R289YFvL/rZgMBV"
    "IMTL53v3CSTfDQj8ruC2JEnh8wWBQhDpDj78HV/SP3GMMTg2Q6NRx8bGBjY3i2g06jAMA4qiIJ1OI5VJI5ZIQFbkoJsQ4ECn3Ua1"
    "UoVj20jEYshlc8ik0yiVy3j44YcxPz8PWZZx/PhxTExMYHBwEJIkhYomECbGGBgBGPfabovFIlZXVmFbFmzbwebmFrLZLAYGBtCT"
    "8wqPTNOEYRjIpDMwLBNrG+uYmZkBAIyNj2N0ZCQUYtu2EY/Hwwj/xsYGOp0Okn4RUCwWQzqdDlN/nHM4joOtrS3U6/Uw8JjP58Pf"
    "t9PpoFQqhXGLbDaLRDzpm85egZDlWL51oYNz+Ca7g3K5AlEUMTY2hlQqhWQyiWQyCUVRIAgCGGPodDqoVqvb8Qvbhu26cLnrNRv5"
    "lpllWTAMA4ZpQJZkpBJJjIyMYHh4GAMDA2g1a/iTD38YrVbLywbACxinUknkcl4aN5PJhJaN99uvYGXJm6tgW1ZYUUoIARUIqN9I"
    "RJ/g7ws7UofwLbLrn3MDjh49Wokp6nfX6vX/fMcPfN+B7AE4ZwogwAc+8AGsr68Kz3veC8YPTRx+xeDg4FsTicT1giQlBVFEp6Oj"
    "0WiE9fMAgqGJOxQAJduxA4ESL823SwF0xxa8WAPZUUMQnBjHcWH7rDi1Wg1ra2uoVevodDrQNC28IFOpFBRFgSiKsF0HjHPAL0Nl"
    "nIcjtThjsH2arlarFZr46XQalmVhdXUVZ8+exdbWFnK5HE6cOIFDhw4hk8lAluXQMmAEcINJN5TCsizUq16sYGurCEophgaHUPD7"
    "ClqtlscwoyioNRpY39zweAo6HWixGNKpFERRRDabRafTQaVS2VF63Nvbi2QyiVar5Vc9Nr3OPwBra2uQJAm9vb1hAVKw2xNCYJqm"
    "1xHpN0EVCgWvfsFhsG2vQ9Ir8+JhdWMQ8xBFEaqqYmTEa6UOdllCSJiR0DQNiqpAluSwSKpWr6Nar6HZ9DoUbdvyuhd98870FYFj"
    "2eh0OqCUopDPAZxhfn4utMICohMCgFICRZGRSCSRSiXR09PjdXYqKggHmq0myuUyzk5OYtNv6GLMgSSJEAXBm7wUWpA0TFGHgkQp"
    "bNvGa173WsRjsXlZkl6nG8Zj3/O27/7OUAABfuqnfwZTU1P0LW9+89DRo8df2dvb++Z0NvscUZaznHMS+Jy1mle6GghrtwALggBJ"
    "8BSAIDy1AqCC95xgCqvruGg2W1hbW8fGxjoajWZYBJPL5ZAvFJBMJLqsBa84wGXMKx6CTy7hfx+XuSG7DQ+IJxmHY9uwfD4A27ah"
    "aV6MIB6Po1KpYm5+DlOTk7BtG8PDw7jyqqswODDgNQiBhJx+jDPfi+FhpWCtVsPKygrazSYk0eMeCFh/XOYik8uF8QbHdaEqCuq+"
    "lbWwsABKKQ4fPozR0VFIkhT6ybIsezwGto3NzU3MzMzAcRyk02lkMpkwZsA5D60i0zQ9xuFKBcViEaZpeqlPNRZW3RVLZehGB4QQ"
    "pFMp5AuFsBHKNC20Wp5lEij84Dw2Gg00Gg2MjY1hwP9tYrEYZFkGCEHLv06q1SqazSaazaY3Lg1eG7Jn0dlw/X4Gr45D9JmNbJim"
    "6f1mrgvXdeD6MQzGXMRiXoYkk84gk81hfHwcExMTsPzfZnFxAWcnz2BjYwO1ag0ipV62atdGEwi3Zds4ceIEbrr5eei0O99IxGKv"
    "N01z/a1vffN+y/iFVQABfvLdP43llWX6ute+dmh0fPzlg0ODr00kEs9XVTVPAMIYg67rXmDK0EPNSqmXEZAEwQvUCNvFQIHL4GUJ"
    "vNRgsGtUq1WUimVUfLoqRd5u6w12eCoIYABcxwXjLEwBBn/BrHsAoXB6sQrseB7nHHB9hUEAy7LRajbRbLVACEEmk0ZPoQeMM6yt"
    "rWFqahobGxtQZBmHjxzBoUOH0N/fD0EUw/RY9+DO4KKyDROlUglLS0uYmZlBb28vDk1MoH/QyzDU63UUSyUMDQ6GArWxsYHZ2Vno"
    "uh627+ZyubDU2Gv4qQEAMpkMRkdHQ7LSVqsFy7JCd2FraysU3JTfdxAMJeXcK9BZWlpCuVzG2NgY8vk8EomEl3nQdY/eTJIgClLY"
    "cLS0vATTMMPqwrExjxLdcV2IgoB0JgNJlqD5cYdAyViWhVarhWKxGBZYmaYJ11fujDHYtsdT4Ak5CysgveCl42cRLBiGDua6sCwT"
    "guDVO7zwhS/EDc95jndu/XJy2/ZaqDc3NjA7M4vpM2e9uIFlgfhuqCAIME0T2WwWb3vb22B5iucThUz2e23X1V/96lfut4w/Jc67"
    "bfKrv/arqDfq9Pixy/tPnrzyxQMD/S9JpVI3ADhGKY1RStHSvR550zT93ncKURB3+PyBPyrLste+W9xEpeIVnziOA1lWkMlk0d/X"
    "H5bgBj5u4HuDELjdAt71+G7Wmu7Hg+Pdj3H/MdaVaQh66qu1Gjrtts/8m0cmk0Gn08H8/DwmJyfRaHjtv0ePHcOhQ4cQj8fDMtgg"
    "eAjulSwGF7dlWVhfX8fa+lrYBtzX1wfOOSqVCkqlEur1OlRVDQN9rut67D/VKsrlMpaXl3Ho0CEcOnQIKb9ysN1uo9FooFAohGnA"
    "SqWCmZkZ1Ot1HDp0yG/9zcJ1Xa+N13Ggqho0TYVpmKjWapibnUOn0wmDffF43C+QMlAslsJMRdIPWgauQMcnG43FYttNSZTCdh00"
    "Wy1omoaRkRHEYrHQ+gusyGqlgnqthmaz6XMiBu3IrneufbZk7tOjMderI7BMw2unNnTYlgXTsnHHHXfghuc8Bx29A9Pv7eCchTEp"
    "7jJ02m2sr61hbm4OMzOzYeB0YGAAL37xi9DX04uFpUU4tv373/3WN//c6dOn+RVXHMwmoAAXzDkZHzuGhcU58ud/8Rfajc99znAm"
    "m3mdJEmvlSTpWiLQOPODUXq7A8s0vYm3QSygyzWoVCo4c+YMBIGip7eAnp4erxBGjcGbye4JEffpr7rhJRXJDqXw7SqA7tcGj3ez"
    "5gaR7qDuPpPJhIG1ctkra11cWgIAjIyM4PixYxgYGICqqt76GQP84SEh3x3xpgfVmw0Ui0XUajXMz8+DMYYTJ05gcHDQr+f3ehU4"
    "52GzT6lUwvr6OpaXl6GqKg4fPhxmF1zXBaU0NPMbDa+9eHh42M+jd0K/PahibDTqKBZLqNVqXlVfKg0tFoPoC2jHr4zcWN9Ef/8A"
    "RkdHkUgkIMty+FsF57h7d6/VaojFY9gslaBpGsbGxpDwXbagRVqWZS8z4Wc7Op0OatUaSuXtXgzTNMGwzTPidSI6APOsAMe2wfw4"
    "ge24eP0bXo/rrr8egiSGtOpB4NF1vPNBKYFABZ+U1US71QYlBKm01+zUbrawubXhuK7zY7pl/uX33nHH9nyFA4oLHp146UtehF94"
    "z6/hoQfvl2+55QVH8j2F2+OJ5OtESbyGEhITqRD6oMGF1+3/N5tNxGIxZDJpv+7fK+11bL/SbNeuH+7+/td1gXOuALqzDN3PC3bv"
    "oJqv2WwikUj40egsDNPE2toaJs+eRalUQiqZxJGjnouQTqWgykr4WeFnAiA+752ue1mEIPAnyzJyuRxyuRwcnx3Ytm0Ui0UUi0Uw"
    "xpBOp0MlY5qmxxZkGNjc3PRmDaZSyOVySCaTIWMP9YlFgjqCYrGIzc1NjI6OYnh4GJlMJjS5A6pyr8qxg3qtgUrF62gcGRlBKpUK"
    "C3IArwegWq2GzVKyLEOLaXAYgyCKSCWTEH12pQCyLEMSRSi+i5BMJiEKnjvV0TtoNpsolkqo1b2Ar2XZcBwXnLvgrgPOGRzbAjgH"
    "c1yveSsWw6GJCQyPDGN4bBSpVCqMY3hVkhYM3XMdCCFwuTdqPSBBBYB2q4VyudSgBG+rN1v/8QPf87YLLV7fMvY1PPnf//1VPPDQ"
    "/dKNz7tlfGho4NUE5I2KJD1HEARNkiTPT7Nt2H4EOFAGHrMN94qJCPV9dPIEoX8qF+BcWwDdx7trHbpTgEFVXqete5Nj0mn09vZ4"
    "RKCtNuZmZzA949UX9PX24sRll2F0ZNRvcPEi8oTSsN05/GTOYVmW52MvLWFjYwPJZDK0PgqFQtgqnEgkQmqyIEC2vLyMarUKVVUx"
    "ODiI3t5eAB7hiSAIofAFdGW1Wi10CYI+gng8HiqMYIev1WpepWPbCJmKRNFrfFIUBcViEfV63S8YKvhZiBSoIKDj7+KBWxVYdoIg"
    "wHIc1KpVWKaJ8fFx9PpNRWpMC3saGOdo+e5NxXeBWs0WbNOA69oA98uTGYdt2Wi226CCV9gVi8fR29uLkTGvTyHghwiUaqfTgcs9"
    "tiPXdvyT79HCNeq1BUkQX6/rnUfueMub9lO8nhEORH7i3z79aUxOnhVedMuLj6ZTqf+RSCRulyTpBCFEDcx/xx+ECSCsESB+aTC4"
    "d+Exl4FxgMEL4DG/zJexYGiEH8nngMt90xpBmfBOiudnqgCCx7pN9e7jgQLoLg4iIDAtE81WEx1dh6ZqyGZzSKfTIOAolUqYnJzE"
    "xto6CICxsTEcPXoUuXwesqpsf4b/u3Q6HVS72IkDywPwqMcD9yPgCgzM/qAVt1qtYm1tLbQCAlqzdDoNQRBQLpdDHsFASQQt0F7B"
    "UdXPGsgQBAGbm5uwLMurOUhlQiIVQigsy/ZNdAMbG+sghCCVSqFQKECSZD/oSMGwrfCDOoTl5eXwN5ZlOay+VBQF7VYbpmVA02KI"
    "xTwrKxaLQ5IEEOopyKafhi4Wi2i1/FSo6+3wDmNwmRvGW7jLQEUBmhZDb18vBoYGMTA4iL7+PiQSSUiSGConvd0GcxwUNzdhdvQH"
    "k4nEGxzXXnr5rQe3BDjAgVAAAPCa21+DT3/m0/jwn/ypdtllJ04MDAy8XtO01wuCcEwQBCXg3982h12vUINSUOIFlIJKNBdsT0vA"
    "UwAuwOm2AvAnygTDJb9VC6D7NcHt3ZZFcMyLEQSElsxXVBytZhuNRguCQJFMeoFDTVXRarWwvLSExcVF1CpVJJIJHDp8GIcPHwal"
    "FOsbG9jY2ECz0fCpvQvIZrPo6enZQXO2tbUVEmsExTCVSgWbm5uhv99dTRgMPul0OlhbW0O1WsWRI0cwPDwcZgiC+Io/awGccbTa"
    "LczPe/X33jp6vRJmUYBl2RCo1DWPj8GyTCz530/TNPT29nr1Gek0ZEUNg5vNZjMMtmUymTD/HjIZAz7VmVdJyRnxzX4bPb15FAp5"
    "pFKJsPjI8BuQNjc38cjDD8PQDa+c13XBurIyjut6A1OYC1AKWVU87sfBIYyOjGJgaAC5XA6SIMI2dMxNz8DotD+bTie/13VZ7ZZb"
    "btlvsXpaHBgFEGBgoAdra1v4vd//I/mG59xwNJ/PvjEei98mCMIVgiCkVFX1Kuw8afbquokQFgVxxmA5DizbDgNNOxUA81qC/dgB"
    "YwycdBX7nCMFsFsJdD/f+3xPiXl1Bxy27YJzBl3vwNANSKKIdCaNXNajGmvUalhYWMD07Cxcx4HjOhBECZdddhyHJyYQj8dDoo1g"
    "9++2PiqVCqanp7G6uhqmxgYHB3HkyJHQ5A84ARzHM2u9YF8D1WoVk5OT3sgzP4Pg7ehesLPRaKBcKqNULoMAOHrsmGeZtL1uP01T"
    "oakaYrEkGGPeeLNaBe22x3swMjISuhABmUi17hGv9vb2YnR0FLlcLvwuwPa8viDX73EmWGAux+raBvROBz09PThy9DA4d2GaRjjX"
    "IZ1OY2xsDK1WCx/72MewurqKXD4PMUjL+hToruPCZR7hicvZDnc0psVQKOSRK+QxPjqKoYF+NGt1WIbx4eHBvp/u6KZ900037bc4"
    "PS0OnAII8L1v/x684c1vwfTUpHLy5NVHBgcHb0smk28WBOEaURQVSZLCtJHretaAKPruAuMwTSvsPLN9ZQAOEL+WmwFwAwWAnQpg"
    "L6F9JlmA4P/g8e7XBReud8wbZ+0G70+o57pwDs49v1TvdNBqtcFcN7zYAn7AUqkM0/Kq3GZnZzE4OICJQ4eQz+dRq9VACEE8Hoeu"
    "61hZWQmpyuPxOMbHx8OUar1eD8tms9ksEokEJEkK+wS2trawubmJTqcTMg4HfQbBdywWi2EaL5/zLBBFUbwBGZYFyzYBAK1mC81m"
    "G2trXkn4oUPj6O3rQTwWBxUEOL5FEcQVHJfDNA1UqlWUiiUUegro7emFJEthKjBwCwVBCDs+2+02ymWvS1MURSQScWia11Yc1AXI"
    "soyBgQEQQnD//fdjamoKA0NDyOSy3rwDl4O5LlzHqwr1akI4HOaGgVXXcUGo576kUykkYhquvvJKl3L8/L3fPP0HL3vx9YgsgHOE"
    "z3/uC3jwkQfka665/thA/8BbNE19jSwrl0myoqmqFwkWRAGi3w/ACfXzwSyMdluWBcd2gEAwCQUL0lHYbk7aXbcf3H4qBbBbSexW"
    "HszfRQLsfp3DOLo7EoNJtNz3sQ3DgKHrkCUZ+VwO6WwWkizBNA0szM9jfn4OjUYd2WwW/f39oekfEJD09PSEVYpBwwuAcFhpMNMg"
    "cAeazWbYPxDEDxKJBDRNQ7vdRrPZ9HfyMur1up+VyaCn0AtQEloSFMQP1BK0Wm1sbXqRfo8UtYVkKolEMhFSkwU8v97622FTlCRJ"
    "Xp1ATIMsyVBUr3swIHQlft+uLEte4ZEogjEXrVYT7bY340D2Yx+SJPlKwqshyeVyXi2H4JHVMJeBuy6Y47kDQeuyy72qQ8t1oMgK"
    "+vv6MDQ0hJ7eHnDGsDA3i/GR0a2YFvsfzVbrv664/DiOHTu236LztLgoFECAj37041heXpUvv/z4yVy+8Pp0OvNqSRJOUEJjiioj"
    "kYwDAJgLSLIMURB8De6CuQyGaXostY4DUAoOnw8AeIIFsNcO/3QWQLfpvSMG0H3M/9FD9wMErCsz0W0p+KaCF99w/Np204TleMw/"
    "2WwW6XQKzLV3ZAACUo+JiQlMTExA0zQA8Cf6uGFGhXOvfn9rawvr6+thUY63cybQ09OD3t7ekFcgeCx4D6/Zp4z5+Xk0m01ks3lk"
    "cnmk0imkk0k4toVq1Q9OVmtQlFjIeuS6DlqdFlrtFlzH9dJ/qopyqYxisQTbsqF1zSHoLojSdT3McARj2gAvLsHBIcsSZFny+kQo"
    "hesy1GpVLC4uhsxMXsWmx8/AAbicwWZ+oNb1LEI3GLLqn5N4IoH+gQEkEwl02h309PZ48xQ5h95p6Qkt9mfJRPJ9tu3Ubrnlefst"
    "Ls8IF5UCAIA3vvHN+MQnPobf/d0PaccvO3p5X1/vKxVFfq2qKleLkqDW63WIgoSREa8OXpKkHUJq2zYM04BpW+EQC48YZFvwnmp3"
    "Dx7f7WfvtfvvUADcMyM5PGqEYAgH48QvVuG+W8B9NwWhAgC82EbAoWjZ3jivjq5DoAT5XNY3dbVw+k6lUsH9998PTdMwODiIiYmJ"
    "0KeXZRnlshcErPuFPD09PRgbG4cW08CYl8Lb2tpCu91GPB4PG6cYY2g0GlhdXUWpVAIADA8PY3BwEK7LoVs2Gs0mTF3H5voadL2N"
    "/oF+DA0OI5PJQZIkz8IRKDjxir8c20Gr2UStWsXqyioSiQSGh0dQKPSA+hTi3b9tkBkAEPIbcO6N45ZlGV5Lv5cB8vgRt0JG53w+"
    "D0EQwiEpgYnv+v0gjLlgtrf7M1/h5fN5DA8Pw7IsnDp1Cvfffz9Wl1fxjh98B66+5how14Usi2eOHj7ypk6nc+bYkYkD3QDUjYtj"
    "lXtAUTIwzRp+4l0/I7/qVbeOFwr521VNeQ0h9JpEPJFWVY0EbcNBHn2bH8CF5XqTbEzTht1l7gF4xhZAcLv78b0UAIOvAPzx2dQn"
    "JnV95ePFAfznOnwnpyH3Jt4yP0tBujrQHMZgGjqMThuu64SVerFYDIQQr5d+dRWrq6toNBrhuDNd15HL5tHb2xum6LzCHAIOBtfd"
    "TrkahoFisYhpn/+AEALLstDf34+BAT8KLkmghMBxORgVAEJh6jpatQo4ODp6B7KsIJlMQVU1P85g+UQwHoWLQDyXxzItv8mqFsYW"
    "gq7BoDIvCHYG5zMgKwlo1BvNGjh30Ww20G63oSha2PAUcE2GFaPB+fTLul2/ZDgggBkZGUEmk4Fj2/jDP/xDfO1rX4NtO9BkBT/1"
    "sz+Na6+9Fo7rQlOV/7ri8sveQgit5rOZ/RaPZ4yLdjy4adYAAB/+49+3Tl5xdOrB+7/xoWPHL//s8MjwKwQqvoQQej0hZNhxHCEo"
    "dZVlL08Nvy01HhegqoBhWjB0A5Zl7ozWn0OE70h23gk3e/9gIPwk5EIJqWm95wUKCR4bjRbTENcUWJaFTqeDjY0N9PT0IJPJIJFI"
    "4MSJE5iYmAipwAzDQDqdBmceDXnACRgMItE0zafzslCtVrG5uYlisQhN0zxzmXPEYrGwDTdQgIR7awyaqjRNQ0Lt93bhThutVhub"
    "m1sA4BckxSHIIkRZAvwBoxTbVOWxWAK6rocUZUFwMChkCgqKAsvNdV20Wi1sbKzDdS1weKPMgkErvCvt232Og35QcA5JEJDPZjHs"
    "1xeYpumNhXNdWIaJSqkM27R83ikvxhFsLMxxNhVJ1A3D3C+R+LZw0SqAbvzIj/wIXvX61zi33PTCqX/793+bf8HNz//4wMDQ1bFE"
    "7A2aqr7CcZwRWZZFx/GGaMqyBCJ4p14UKVSiQhQE2LYckk7s8MXPIXZyHHVrAwK/UyEsYO/mpSFdw04A+DvWdppPkqRwLHlQbx+Q"
    "fRBCUCgUUCgUwu7JRx99DF/96tfCIR59fb1hurBWr4bFPPl8HocOHQqpzrv98FqthsXFRe952Twy+TyUWMKzblzHy2hw5s8piCOf"
    "7/G4D/zWZU6BZCqJZCIJVVFBOUK/m1IhHGGWy+XCUuRSqYRyuezRlPsBy+XlZTQadZimhVQ6iYnDE1AUqSsD4/FBdpvl3YpLliT0"
    "9PZiaHgYmqZhbXUVn/vMZ/CNb34TV15xEm9729tCq8FxHEiSFGY6fPeNgZAziUTS6OjGfovDt4RLQgEAwBc++Rl84ZOfAQD7S7ed"
    "2njkPz638c8f+8TXRwYHbozH429JJhIvkyRpzJVkyXFsCD5ZBeee0AWdZkHPvOEH3EL/0/+c4HZALBkc2w2PgJiEGQavZNkXbrLj"
    "WQAAwgnAKZjPQxdwExAEk3O7XRHAY0b00p6ypkCLaRCox4roOG7IY+ApCnjXqG9xqFoc113/HLRabRQ3t7C8vIqpqRkomop6vYa+"
    "3gImDh9BPpeDLEngHHBcj90nnUpBFCSoCkcqmUKpVEa1UsPGRhG5fA/S6Qxy+TximgpRlsBcBwQcrsvDhiLPnM+h1W6h2W6jUVsD"
    "BUEmnUYqkYBARXT8QF/gwgWlxIahY6tUxNT0pDck1XWQSCYxMBgMe5X8mYKe0DPml4n7v6DLGJjjggoU6VQSQ0PD6OkpgHGOe++9"
    "B1+/605MTU6i1WxANwwcGhvzjS+v+jCRSIS1I57rAtiOM2k4zpc++q8fxw03PXe/ReFbwiWjALrx6Of/A4QQvOd//XzrH/7PA//1"
    "Pd/7jgeHh4dviMeTdyQSydslWe5VFIUwl0EQBQh+ioj53XdByWzA69/Rdbh+nnq3qHeTj+4oCIJPctp9wHvBjucGm5LXy7Bjz0fo"
    "GPgMtYy5cF0OWVagKCpURQOhAHMtcPgdb26gYHyyCh5YD4EQ+CSqgohEMoV0Mo3R0THU6jWUqzUcmjiMrc011OsNpFJpxDSPkowS"
    "AclEEvV6I3QnSqUSEokETp48iWy+ANtysL6xjoX5OSiyjHgijkI+j0QyAdt2vM/1KzY9qq40EsmUPwmojUa9gVq54vUX+H0LnU7H"
    "J/vwMg6ra6uoVivo6+vF0NAgBIFCi8X8kvBu857siNsEj4migJw/Ek2WJCwsLMKxvXX/6Z/8CUSBYmCgDyevOIFTp06DczccMBKs"
    "O5vNYnBw0E6l06Vms/mAoet/39fX85CYy+LI2Nh+X/7fEi5JBRDgN3/rdwAAV13znOqHPvRHX/r5n3/PA7lc/rPJVOotiUTiBZqm"
    "DRGbCjAMiJIMRdF2CLQgCGGxkTck0w6LT6i/uzO2k8ij27fcLfwkOLrNgdo1DnsnA3J3h2HIkiTJiMdjUFXN64B0PGrsoEMN8OIC"
    "zC+K2U46ouuTdsJxXRBK0dfXj0Jvr98zwbG8vIT5+QVkUukwDbe6uoJGow5RFJHL5XDddddBURQvDecHMmMxFelUEh29A9tysLy8"
    "DNMywxLkoCEoqHdgnEMgBLlcDpl0BpZpotVoou6XMAfsx8Vi0Wc6ToZFT6IowHZ8xbyrOxPYGbiNJ7wRZcPDwyAAvvCFL+Duu+/G"
    "7Owc3vTGNyGfywEcuObqq9FsNnB28qzPX5ACAFBK+MjIiF4oFNavuvLKhzPZ7P2CIN43v7R0tlqpFv/9s592/ulv/2a/L/lvGRdt"
    "FuDbwS//8q/iX/7lH/GLv/Qr+cHBoRekUqk3xePxlyqKMuhyEBAStssCgG1ZIXcf4O0AQRddUIkGPJEtKLiwdz6G8D7g+/Bdvunu"
    "6sHgM7srHre5Dm24rucrewzrHG7QywCvxsANZqDtSGeSMOvgMn9tjIestww+Dz5YOL13bWUVm5ub0HUdmYwXNBwfH9sxFKVUKkFV"
    "Y2DMhSh6rcCEUDSbLWxsbmDTn+mXTqd3sDQxANVqFZLP+6ApKgRBgG1aKFcqWFxahK7rIZ1bT08PFEWGN+glKKV+YhEWsK2YM5kM"
    "BgYH0dPTA01TQamAqclJ/NzP/ixkxeMifMlLXopCLos/+ZMPew1NIoUkiRgeGsX3fu/3OkNDQxu6od9f3Co+ZOjm3ZSSh+Mxpbry"
    "0JQ7fu1leO2b3rDfl/a3jUvaAtiN973vvQCAqcmz5a/f9bXPPP/5t9w9MDh0cyaTeYsoii/hnPcbnTZNJrwBHbIsgwrU43x3WFhi"
    "Gwz2CFh4d198zwSB5vVM++0ioqDdOXBBgjJX23a9SkZid3UvepEC6tsWAQEGD4Yg7jBDgk/d6aaEPOrUt0/CISl+mevlaRw5ciT8"
    "fvfffz/W1tbR29sbNu9oWhzpdAqmaaDZauDxU4tot1uoVmpwHBcnrrgCY2NjIclGtVrF5tYmZFlB2icYsS0LlbZHG7axsRFW6V15"
    "5ZUhDVzA7ecx9XjWjhfXCLo+GQihYV1DMLbNY3gGmMsA7gJgGBjox9joKObn5iEQQFVVnzFYQzKZ5D29hcZ11143mc/nv76ysvKf"
    "pXL1kaWlpfJdd91rqrKG//zPT+735XxO8B2lAAL8xm/8BgCwakUrfvwT3/+pv/zL//PV0bHRF2ia9t2KorysbJp9tEpJIpFAMpmE"
    "rKqQJOqzynhDJzVNhSxLsG0nZKEBun178qQKYVtheBaAF/H2dnlNU3eYyJZl+zFAv9mJB0LM/TmIBNztDjH4DgXfbd6RHbeDrALx"
    "4wW+9IdDVHhQMwEOURL9NXBce+21WF9bx8bmBtbW1ryRXoODcByPFXljcx2qKiOZTOP48ePo6++HIEjQ2x2PN0CLIZ1Kw3FsNFst"
    "LC0thbRunVY7nKFw/PhxxOPx8PcKOikBj+GXY5urkbFgurI36ai3pxfNVguPPPIw7rzza3jZrbfilltuge1aoWVVq1WxvroKUZBQ"
    "yOdxww3X83K52KzVagsjIyOP9Q/2f9UyzLs/86lPzf7+H/yecfnll+PMmTP7femec3xHuQBPhp/6/34Wjz1+itxxx5t7enp7X55O"
    "p1+vKMoLBUHodV0XWtzrkU/EE2Cc+yW1Dgj1JuEGfeGGYUDXdW+n2tVIxPyCnmDn9ghPBb+NVYUgiH5LMn9CFyPgjTTz3AoWPo+D"
    "eSY+22Yy9mYkeS4B8cgRdrkg3p/L+Y74RbDOYH3dsQrvwfAfjyOfEDQadayurmFjYx2GrkNRJGSyaRw9egTZbA6cEbTbHZ+Nh4eM"
    "w7Zte8zH/oTfXC4HzjnSPvEo9Ye4MOaGrkug2OB3UXrcDwyqqiCbyaCv36vN39zawj/90z/hgQceQK1WA+cc73jHO/D6178ujN8s"
    "Lizgt3/rt9HpdHBk4oh7xx1v3erp7b2vUqncVSqV7uaMTT762GN1TdPcX/nlX9zvy/O8IlIAXXjPr/4aGtW2cPKKY4XBwYGbU8nU"
    "9yiy8jwO3kcIEYIpPQFVlGXbcDnC8lSPmdbrpNMNwysi6fL1OQKufMUfF71dkea6nmXRTU7SrQCCXPZ26tCraGScAYyEzUZe1aFP"
    "gMIAzroFm4Az7zNYQIUe1BmFuynbkS+n3bELvzpp97gsy7JgGSYkWcCp04+j1WpgZGQMA32DUJQYuD+Xr9FohMQj7XYb8UQc44cO"
    "oVAobH8GvFoAztzQOwktGkLAXG9acNpnU0okttmEQAn+7d//HR/5yEcwOjqKWCyG2dlZvOUtb8Yb3vB6b9YBAMMw3C/9539WdV1f"
    "GhgYvDeXyX3u7Nmph77xjQfK87P/z4onjuC/v/L1/b4cLwgONmPhBcZdX/0Kvnnf3fzkyZPtj3/io2eHh0b/23Xdx3xm4oJpmolm"
    "s0lM0/R2blWF4JOUdAuPoijQ/Hy3pqqeX5lIIqbFEI/FIct+kQpjHr+9y0L/O6im25uqLKxG2PW4/5pdaUevhqD7G5Lut/BKk8n2"
    "Q37Tgn9/O3tAuqoVA9cB2C6JFkURsqIAxDPDBUHA2to6pqZnUalUYRoGZmZmcPr0abTbbfT09OD48eM4fPgw4vHEjnPAQ9/FUziU"
    "0nBEHCFAPp/HkcNHkEwmMTl5Fp/4xCcgCAKOHz8OxjlOnz6NyclJtFotzM7OwrZtvOAFL8CRI0fgOE5H1/WzlXL5/8Vi2l+Jovjn"
    "rsv+5fff94HTY0cOtT784Q+6q2ttLCws7/eleMHwHRkDeDr89m/9JgDg6LHjxaWlxU+/5vbX3TM4OHRzPBa/Q9O0l7RarUKz2aSq"
    "FkMmm0UsHvfjAzuJQoL0XVDSG+TAGfeGW4DT8HkBwtbkLuwmHNlZPUjACLxJRowBIEGmP3y/7Rd3pwSx4zPBeTj5hnVVIwaNyoFg"
    "dtfgB/CyEV6jUjyewKFDcYyMjKHZ7GB1ZQ1LS0vQNA3XXHNNSLYZKjDGQP3P5OFvQbw+AeaZ/PG4V4Y8PDwMo2Pgn//pn/HNb34T"
    "nY43nenqq69GEBAFgHK5jEwmg2uvvdYdGBgwRkdHN4pbxTPr6+tf29rc/OrczPTs/NxCLZlMuH/yp38KALjv0Yf2+7LbF0QK4Cnw"
    "l3/+EQBg/Zdft/m3f/Z3n/zwj/7A1wb6+m9JJBK3aZp2Y6fVnmi12skgWKjFvWk53tRan7kGCCPtYaSfUL9SL2jw2eYqDEQ3yMfv"
    "FFYeKhMe3t4+zEFA+LYK2BZhH2TbffB29u336Lr5BLDgXYKUIeG7FBHCeIT/QaBUQiqdQTabh20dD0dth7EN35UglHoxSE5BXD+2"
    "wTlEkSKZSGFkeNgb45XJQJEk/Mfnv4C77/46hoaGIIr9WF1dDddPONDX29t54S23VEZGRqb6+/sf7+ntnauUKw/dc/fdZ75xz72V"
    "Fzz/+e573/vr+31pHRhECuAZ4G9/7zcBgP/LP2bLd339G5/64B++/8sjI4OH0+n0rUSgb2w1m1e1Wq2YoqrI5XOIxWKQRObxyblu"
    "12BJwN9G/XnyXTUCpDsgw7uEyb+/WzyDeEBXcG4be+/03cIPdHcdklBRBf0Fe78dCd9m+6sEn+FZH0GZcnA7jI8E70uIN323qxKS"
    "+a4QgUdimk4lMTjch76+Xm8M+3YwwGcO8gqVarUaFEVBKpVihKDtWu7p40ePfVEA+QbnfK5Rb658+A9+r/2K21/j/vL//t8AgM98"
    "5tP7fDUdLEQK4FvAXV//PADwufnHG8eOH39ocurs6f6Bwf9IJBK3SZL01k6rdUVH78Q0TQspuBVFDtl3AYRpNmC3ef6EI88IByeK"
    "G/bV+fc8OyTYmknX7eB7MuYN3BAEAcm0xww82N+HdCYFURZDC4m5LHQ7Ai6AVCrFrr766ubRI0dmDx0af6BWq31ldXX94Uceemjh"
    "C1/4pP66172R/8A7fhAA8JnP/cd+/zgHFgfn+rlI8alPfhaLy0vi4ODQMVlR3ijK0htEUTzBOddkWUYum0U6kwE4h+VPowEHGMGO"
    "SkK/Y8dnKdrJTbDjz99IvRy9F28I6uEY46EL8HTMRtumOMD49mWwOzUYIFjjDiuFPEnxE+9WBtxLRSBgXw4YmHlYUjzQ34eefAGP"
    "Pf44TMPEi190C1igKPy1CsRTJ/ff/0D7n//lo4sTExOnjx87/lUtHrurr6d36qP/9Nf6iSuux1vveMt+XxIXFSIFcA6QTF6JRuNR"
    "/Nbv/XFsaKD38lQ6eZumqq8HcDkhRJVECZlsBulUGpIkoaMbcLoYgTlnl5YCAA0zB55P7/jvy0EoRTwWQ6Enj/7eXiwtLUGRZUxM"
    "HMIv/PwvgBCK3/3d34EW1xDEA8C56zpumTH20Mbm5udmZ+cezGZzsw/c/2DxxS+6xT1+2cHn3juoiFyAc4Bm8zEQQpAEOmfK7fv/"
    "+sN/8OjRY8f/LZmIv55Q+nrO2Imtzc14pVz2Rm/lC1BkDYbhkZUC6Mp5H2DsKi3eK1tBfIafIODHucewI/o05729PTANE8MjQyAA"
    "PvKRP8dA/wB+6J3vxPr6msfW6232jHPetG17xjatr9i2/ZXJycn7P/vZz26dOHGCvfzWl+33r3FJIFIA5xBNAMP5OABY3/jmg6fu"
    "uvPO6Uwu+5lsJvNdqqq+0TTNK4rFolat1ZDK5pBOZ8JhnrZpeKYy2U4N7igr7o767xMC4d6+T3coAa+QCQjNFHDENBXZTB8GBvqR"
    "y+Wwvr6G3/j99+NNb3oTrrnmaszOziCXzSKeiOGWW17Ajxw50hEonW+3WvdVqtW7G/X6PRtrG/M33HC98fznP39/f4BLEJECOE94"
    "7nOuw/vf9z4rmYk9Oj19dmpoZOTzyWTyNQKlb7UsfmRjfUMtl6tIpzPo6clDSSRgWSYs2wm7AwPwoIx4HzUAIX6KsbuLyW9f7uZa"
    "BPdKhROJOPr7+lDI55FMxkCpAEkUsLAwj0cefggvetEt0DQVV111Fb/xxhudRCJRfstb3vJNx3G+MDc3d89dd94196EPfaj5Xbd/"
    "F/ud3/mdfTyTlzaiGMAFwA3Puw4feO9v4tTpx+VsJnciFk++XlZjtxMqngBIXBQp0qkE8rksJFn1mIt9ptudfnxQHHPhYwAA/PcO"
    "4MUAwuInwqHKMvL5HAr5PHryOaiKAuoXPwGAKAr4xjfuwwc/+EH8xE/8OLvxpueVp6ZmHlIV5UHTNO/kHPeqqljrdHTmFfdEON+I"
    "FMAFxgf/6q/QqlS0XK7neDKeelUimXwjwE4SuBoBkExn0VPogaoq2wNNgmwB42AHRAEEBCaEEMRiGvI9efQU8kglk1Bkyc/2ueG8"
    "hYDLoFqtVh999JHTo6Mjj3d08yulcuXee++5d+N/v+cXjFff9hZ8/gsf3+9T9B2FSAHsEx4/tYBPf/oTcjqXPZJKJ2+Lq8pbBUE4"
    "6bhuTKBCyNirxTSvVVbX4bos5AgMououZ/ALi71imqBSkCPskd+TkKSb2rzLswiGlQTw2H539SNwQJZE5HJZ5PMF5LIZKDEZgkDD"
    "3H+Q9+eexrJM01xvt9vfNAzjM8Xi5j333vuN9Xe/+92d4/zYfOUAAAWbSURBVMeP8cnJqf0+Hd+xiBTAPuN3fu8P0Gq2xOGhoRNa"
    "THtdLBZ7IyHkMkKIBgCpVBKZTBZaPAHbdWGbpkcMAn/iEQdc4nUAesSi29V9XjdiMFRjJxdhtwLoPu4yBhAhvO/1AXgqhv//7d1b"
    "bBRVGAfw/zlz3Znd2dntFRpDIgnhlmh8kDT6oEIEgZCgQn3hxVLio0IaeYD4ojEB7IOGQBS5JyQqCYYoPCiXQqlAuES5GW6NlKWs"
    "bNvt3rrdmXN8mC2tookm6rb0+71ssk+7ZzPfzM585/8xwDAN1FRVoaa6BhHbhqEbQTcf98FZ0ACkcA4IWfK8Uk9mIHMpmUyeSqVS"
    "HYlE4sfW1tZUU1MT2traKr30BFQAxoRVLSvx7PMv4H5PIuSGndm2bc81TGO+qqpPMcainHNuWjaqqqvhOA48z0MulxvJHSg/JRBC"
    "gMnhZB9ZbsX1R10BsD+/AhDy4c09IQR8ifL2Zg8cDJqmwomEEauKw425sMxg1BiTgMp5EJqpQni+N6gwnhosFBKZ/vTR/v7+9vPn"
    "z18+cuRIz969e4cqvc7kUVQAxpDXX1+KN1tW4/C3+9WZM2bWRxxnjqoqi1RVexFgT/hCKCHbRnVVdTCTDgzZfB7F0nAWfXCAs3J6"
    "zx9vII5Oyg1CREZ2EwkR/MEXwodgAkxKhEwT8XgcsZiLqONAHzV+nDEGBUwqnBeE8H/xpHd2sDh4qvfBgwu9qd7ujhMnfl27di0d"
    "9GMcFYAxalXLSuzZvQ0bP9ocd93Yc4ZhvsY4m+f5crJkjBmhEGpq6mCHw5DwUSwGU4QBBlYO+wSCVykeDQUdHoUFYCROG8HTvYhj"
    "w426cN0oQqYJzoNn/qw8UUlKWeKc35e+/1MumzuayWQ6uxPd195fv6538ZIlYk1ra6WXj/xNVADGuA0bNuHkiePs5fkL47FYrFHV"
    "9SZPypcklDpfCEXTNUyaVFse9yVQyBdQKpXKAZjDZ/vReQLl9mP8PhJM1zU4jgPXjcKyg/36ClfAedDgo6mqzxnvk8BlIcT3fb19"
    "pxLdd34+3n6sZ/269V795Hr0JHoqvVzkH6ICME6sWLEMe/Z8iU82b41b4UijpumLJeNzfeFNUVSmh8wQ6mprURWLw/PFwzHonlcq"
    "DwwRD8/+nPNyWAmHbhiwLRuWZUHV1HLabtDMo6qKUBQlK4V/2/e804V84Zg3JDo7TrZ3N7c0e+NlAi75a/QLjjNr3n4HX+zYgtUf"
    "tLl2KPKMETIWMy5eYYxPNQ1Tcx0XUTeKqBMNIsURDN70St5IeKiU4AqHogRtx8M9/KqqQgneH1IU5X6pVPyhWCgcSz1Inbl548aN"
    "Xbt2pKdPnyG3bNla6WUg/xIqAOPUWy3N6PzuEJpb37MtKzRN1dSFETuyyAlHZhumGTZ0nVm2DTsSDrLxdQMD6QHcu3cvuPRnojwP"
    "kUPTdOi65qmqlhJCnCuVho7m8rmT2Uz6+sdtbf0HD37z30xKJRVHewHGqa2ffQ4ASHbdyj3ZOOfC3Zu3LjfU1H+tMmWBpmoLoMqn"
    "pRBxIQTzPA+aqqE4VEQmkwEgoekKDF0TjCkDvs+up9O504PFYkcymew8dODA3Z27d9Ml/gRAv/BjYun8V7H/8FfY+OEmY3JDQ0Nt"
    "XX2jG4/Ni0TCcyzbrrEsK5JOp3H7dteg73v9isavK5xfyBfyF1O9qYt9fX13dn66LTtz1iy5b9++Sn8d8j+hAvAYanqjBYcOt7O2"
    "Te9GGhoaptq2NcUwzGnZbI4nk8muYnHwTq6Q7Tp39kxy+/adJSsUQr482YhMLFQAJojly5YrQ0MldvXqNU9RFVy5cqnSH4kQQggh"
    "hBBCCCGEEEIIIYQQQgghhBBCCCGEEEIIIYQQQgghhBBCCCGEEEIIIYQQQgghhBBCJp7fAE+bGq61cwzCAAAAAElFTkSuQmCC"
)


def _make_icon_from_img(img: QImage) -> QIcon:
    """Build a QIcon with multiple sizes from a source QImage."""
    icon = QIcon()
    for size in (16, 32, 64, 128, 256):
        scaled = img.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        icon.addPixmap(QPixmap.fromImage(scaled))
    return icon


def _create_icon() -> QIcon:
    """Load the app icon from bundled data.

    Priority:
      1. ``favicon.png`` next to the frozen executable (bundled via PyInstaller).
      2. Base64-embedded favicon PNG (``_FAVICON_B64``).
      3. ``favicon.ico`` from known file paths.
      4. Programmatic green-circle with "M".
    """
    # 1. Bundled favicon.png (next to the frozen exe)
    bundled_png = os.path.join(os.path.dirname(sys.executable), "favicon.png")
    if os.path.isfile(bundled_png):
        try:
            img = QImage(bundled_png)
            if not img.isNull():
                logger.info("Loaded favicon from %s", bundled_png)
                return _make_icon_from_img(img)
        except Exception:
            logger.warning("Failed to load %s", bundled_png)

    # 2. Base64-embedded PNG
    try:
        data = QByteArray.fromBase64(_FAVICON_B64.encode())
        img = QImage.fromData(data, "PNG")
        if not img.isNull():
            logger.info("Loaded favicon from base64 constant")
            return _make_icon_from_img(img)
    except Exception:
        logger.warning("Failed to decode embedded favicon, trying file paths.")

    # 3. File-path fallback
    candidates = [
        os.path.join(os.path.dirname(sys.executable), "favicon.ico"),
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "favicon.ico"),
        "favicon.ico",
    ]
    for path in candidates:
        if os.path.isfile(path):
            logger.info("Loaded favicon from %s", path)
            try:
                img = QImage(path)
                if not img.isNull():
                    return _make_icon_from_img(img)
            except Exception:
                pass

    # 4. Programmatic green circle with "M"
    logger.warning("All icon sources failed — using programmatic fallback")
    size = 64
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(QColor("#4CAF50"))
    painter.setPen(QPen(QColor("#388E3C"), 2))
    painter.drawEllipse(2, 2, size - 4, size - 4)
    painter.setPen(QPen(Qt.white, 2))
    font = QFont("Segoe UI", 28, QFont.Bold)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignCenter, "M")
    painter.end()
    return QIcon(pixmap)


class TrayIcon(QSystemTrayIcon):
    """System tray icon with a context menu.

    Connects to the ActivityMonitor via the *state_updated* signal so the tray
    tooltip and dashboard stay in sync.
    """

    def __init__(self, db: Database):
        super().__init__()
        self._db = db
        self._monitor = None

        self.setIcon(_create_icon())
        self.setToolTip("Laptop Momentum")

        # Dashboard window (lazy-created, hidden on close).
        self._dashboard: Dashboard | None = None

        # ---------- Context menu ----------
        menu = QMenu()

        self._show_status_action = menu.addAction("Show Status")
        self._open_dashboard_action = menu.addAction("Open Dashboard")
        menu.addSeparator()

        self._toggle_notifications_action = QAction("Notifications: On", self)
        self._toggle_notifications_action.setCheckable(True)
        self._toggle_notifications_action.setChecked(True)
        menu.addAction(self._toggle_notifications_action)

        self._toggle_freeze_action = QAction("Freeze Streak This Week", self)
        self._toggle_freeze_action.setCheckable(True)
        freeze_key = f"freeze_used_{config.get_week_key()}"
        self._toggle_freeze_action.setChecked(self._db.get_setting(freeze_key) == "1")
        menu.addAction(self._toggle_freeze_action)

        self._toggle_vacation_action = QAction("Vacation Mode", self)
        self._toggle_vacation_action.setCheckable(True)
        self._toggle_vacation_action.setChecked(self._db.get_setting("vacation_mode") == "1")
        menu.addAction(self._toggle_vacation_action)

        self._autostart_action = QAction("Run at Login", self)
        self._autostart_action.setCheckable(True)
        autostart = AutostartManager()
        self._autostart_action.setChecked(autostart.is_enabled())
        menu.addAction(self._autostart_action)

        self._toggle_phone_reminder_action = QAction("Phone Reminder", self)
        self._toggle_phone_reminder_action.setCheckable(True)
        self._toggle_phone_reminder_action.setChecked(self._db.get_setting("phone_reminder_enabled") == "1")
        self._toggle_phone_reminder_action.setEnabled(
            bool(config.NTFY_TOPIC))
        menu.addAction(self._toggle_phone_reminder_action)

        self._daily_target_action = menu.addAction("Set Daily Target...")

        menu.addSeparator()
        self._rules_action = menu.addAction("Rules...")
        self._export_action = menu.addAction("Export Data (CSV)...")
        self._restart_action = menu.addAction("Restart App")
        menu.addSeparator()
        self._reset_action = menu.addAction("Reset All Progress...")
        self._exit_action = menu.addAction("Exit")

        self.setContextMenu(menu)
        self._menu = menu  # keep a reference to prevent GC

        # ---------- Connections ----------
        self._show_status_action.triggered.connect(self._show_status)
        self._open_dashboard_action.triggered.connect(self._open_dashboard)
        self._toggle_notifications_action.toggled.connect(self._toggle_notifications)
        self._toggle_freeze_action.toggled.connect(self._toggle_freeze)
        self._toggle_vacation_action.toggled.connect(self._toggle_vacation)
        self._toggle_phone_reminder_action.toggled.connect(self._toggle_phone_reminder)
        self._autostart_action.triggered.connect(self._toggle_autostart)
        self._daily_target_action.triggered.connect(self._set_daily_target)
        self._rules_action.triggered.connect(self._show_rules)
        self._export_action.triggered.connect(self._export_csv)
        self._restart_action.triggered.connect(self._restart_app)
        self._reset_action.triggered.connect(self._reset_progress)
        self._exit_action.triggered.connect(self._exit_app)

        # Clicking the icon — deferred with a zero-timer so it never interrupts
        # the native context menu (which can cause a crash on Windows).
        self.activated.connect(self._on_activated)

        # Track latest state for tooltip updates.
        self._latest_state: dict = {}

    def set_monitor(self, monitor):
        """Wire up the ActivityMonitor after construction (breaks circular
        dependency — monitor needs the tray for notifications)."""
        self._monitor = monitor
        monitor.state_updated.connect(self._on_state_updated)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------
    def _show_status(self):
        """Show a temporary balloon with the current streak and today's stats."""
        s = self._latest_state
        if not s:
            logger.debug("Show status skipped — no state yet")
            return
        lines = [
            f"Streak: {s['current_streak']} day{'s' if s['current_streak'] != 1 else ''}",
            f"Today:  {s['today_active_minutes']} min  |  {s['today_points']} pts",
            f"Week:   {s['weekly_points']} / {s['weekly_target']} pts",
            f"Lifelines: {s['lifelines']}",
        ]
        debt = s.get("lifeline_debt", 0)
        if debt > 0:
            lines.append(f"Debt: {debt}")
        vacation = s.get("vacation_mode", False)
        if vacation:
            lines.append(f"Vacation: {s.get('vacation_days_used', 0)}/{config.VACATION_MAX_DAYS} days")
        self.showMessage("Laptop Momentum", "\n".join(lines),
                         QSystemTrayIcon.Information, 5000)

    def _open_dashboard(self):
        logger.info("_open_dashboard called, monitor=%s, dashboard_exists=%s",
                    self._monitor is not None, self._dashboard is not None)
        if self._monitor is None:
            logger.warning("Dashboard requested before monitor is ready")
            return
        try:
            if self._dashboard is None:
                self._dashboard = Dashboard(self._monitor.get_state)
                logger.info("Dashboard widget created successfully")
            self._dashboard.show()
            self._dashboard.raise_()
            self._dashboard.activateWindow()
            v = self._dashboard.isVisible()
            w = self._dashboard.width()
            h = self._dashboard.height()
            x = self._dashboard.x()
            y = self._dashboard.y()
            logger.info("Dashboard shown: visible=%s, size=%dx%d, pos=(%d,%d)",
                        v, w, h, x, y)
        except Exception:
            logger.exception("Failed to open dashboard")

    def _toggle_notifications(self, checked: bool):
        # The NotificationManager is accessed through the monitor.
        # We store the toggle state in settings for persistence.
        self._db.set_setting("notifications_enabled", "1" if checked else "0")
        self._update_notification_action_text(checked)

    def _update_notification_action_text(self, enabled: bool):
        self._toggle_notifications_action.setText(
            "Notifications: On" if enabled else "Notifications: Off")

    def _toggle_freeze(self, checked: bool):
        freeze_key = f"freeze_used_{config.get_week_key()}"
        self._db.set_setting(freeze_key, "1" if checked else "0")
        if checked:
            self._db.add_event("settings", "Streak freeze activated")
            self._toggle_freeze_action.setText("Freeze Streak This Week (Active)")
        else:
            self._db.add_event("settings", "Streak freeze deactivated")
            self._toggle_freeze_action.setText("Freeze Streak This Week")

    def _toggle_vacation(self, checked: bool):
        self._db.set_setting("vacation_mode", "1" if checked else "0")
        if checked:
            self._db.set_setting("vacation_days_used", "0")
            self._db.add_event("settings", "Vacation mode activated")
            self._notify_vacation("Started")
        else:
            self._db.add_event("settings", "Vacation mode deactivated")
            self._notify_vacation("Ended")
        if self._monitor:
            self._monitor.refresh_state()

    def _toggle_phone_reminder(self, checked: bool):
        self._db.set_setting("phone_reminder_enabled", "1" if checked else "0")
        if checked:
            self._db.add_event("settings", "Phone reminder enabled")
        else:
            self._db.add_event("settings", "Phone reminder disabled")

    def _set_daily_target(self):
        from PySide6.QtWidgets import QInputDialog
        current = self._db.get_daily_target()
        value, ok = QInputDialog.getInt(
            None, "Set Daily Target",
            f"Daily active minutes goal ({config.DAILY_TARGET_MIN}–{config.DAILY_TARGET_MAX}):",
            value=current,
            minValue=config.DAILY_TARGET_MIN,
            maxValue=config.DAILY_TARGET_MAX,
        )
        if ok:
            self._db.set_daily_target(value)
            self._db.add_event("settings", f"Daily target set to {value} min")
            if self._monitor:
                self._monitor.refresh_state()

    def _notify_vacation(self, status: str):
        try:
            self.showMessage(
                "Vacation Mode",
                f"{status}. Your streak is protected — each day off consumes a lifeline.",
                QSystemTrayIcon.Information, 5000,
            )
        except Exception:
            pass

    def _export_csv(self):
        """Export daily stats to a CSV file."""
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(
            None, "Export Data", "momentum_export.csv",
            "CSV Files (*.csv)",
        )
        if not path:
            return
        ok = self._db.export_csv(path)
        if ok:
            self._db.add_event("export", f"Data exported to {path}")
            self.showMessage("Laptop Momentum",
                             f"Data exported to {path}",
                             QSystemTrayIcon.Information, 5000)
        else:
            self.showMessage("Laptop Momentum",
                             "Export failed — check the log for details.",
                             QSystemTrayIcon.Warning, 5000)

    def _toggle_autostart(self, checked: bool):
        mgr = AutostartManager()
        if checked:
            ok = mgr.enable()
            if ok:
                self._db.add_event("settings", "Autostart enabled")
        else:
            ok = mgr.disable()
            if ok:
                self._db.add_event("settings", "Autostart disabled")
        if not ok:
            QMessageBox.warning(None, "Autostart",
                                "Failed to update autostart setting.")
            self._autostart_action.setChecked(mgr.is_enabled())

    def _show_rules(self):
        dlg = QDialog()
        dlg.setWindowTitle("Laptop Momentum — Rules")
        dlg.resize(520, 520)
        layout = QVBoxLayout(dlg)
        browser = QTextBrowser()
        browser.setOpenExternalLinks(False)
        browser.setHtml(_RULES_TEXT)
        layout.addWidget(browser)
        dlg.setLayout(layout)
        dlg.exec()

    def _restart_app(self):
        """Quit the current process and spawn a fresh one.

        For the frozen exe we write a temporary .bat that waits 2 seconds
        (to let the old process fully exit) and then launches the exe fresh.
        For source runs we use QProcess.startDetached directly.
        """
        import subprocess, tempfile
        import __main__
        self._monitor.stop()
        exe = getattr(__main__, "_SAVED_EXECUTABLE", sys.executable)

        if getattr(sys, "frozen", False):
            bat_content = (
                f'@echo off\r\n'
                f'timeout /t 2 /nobreak >nul\r\n'
                f'start "" "{exe}"\r\n'
            )
            bat_path = os.path.join(tempfile.gettempdir(),
                                    "restart_laptop_momentum.bat")
            try:
                with open(bat_path, "w") as f:
                    f.write(bat_content)
                subprocess.Popen(
                    ["cmd", "/c", bat_path],
                    close_fds=True,
                    creationflags=subprocess.DETACHED_PROCESS,
                )
            except Exception as exc:
                logger.exception("Failed to launch restart helper: %s", exc)
        else:
            script = os.path.abspath(sys.argv[0])
            QProcess.startDetached(exe, [script])

        QApplication.instance().quit()

    def _exit_app(self):
        self._monitor.stop()
        QApplication.instance().quit()

    def _reset_progress(self):
        """Wipe all progress after user confirmation."""
        reply = QMessageBox.question(
            None, "Reset All Progress",
            "This will permanently delete ALL your streak data, points, "
            "and history.\n\nAre you sure?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        reply2 = QMessageBox.question(
            None, "Are You Absolutely Sure?",
            "This cannot be undone. Your entire history will be gone.\n\n"
            "Proceed?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply2 != QMessageBox.Yes:
            return
        self._monitor.stop()
        self._db.reset_all()
        # Reinit monitor with fresh state.
        self._monitor.start()
        self._monitor.refresh_state()
        self.showMessage("Laptop Momentum",
                         "All progress has been reset. Starting fresh!",
                         QSystemTrayIcon.Information, 5000)

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason):
        """Handle tray icon clicks.

        On some Windows versions a right-click can emit *Trigger* just before
        *Context*, which can crash the tray.  We only react to DoubleClick and
        MiddleClick and defer the action via a zero-timer so it never interrupts
        the native context-menu event processing.
        """
        if reason not in (QSystemTrayIcon.DoubleClick, QSystemTrayIcon.MiddleClick):
            return
        try:
            QTimer.singleShot(0, self._open_dashboard)
        except Exception:
            logger.exception("Error deferring dashboard open")

    def _on_state_updated(self, state: dict):
        self._latest_state = state
        self.setToolTip(
            f"Laptop Momentum\n"
            f"Streak: {state['current_streak']}d  |  "
            f"Week: {state['weekly_points']} / {state['weekly_target']} pts\n"
            f"Today: {state['today_active_minutes']} min"
        )
        # Refresh freeze action checkbox for the current week.
        freeze_key = f"freeze_used_{config.get_week_key()}"
        freeze_active = self._db.get_setting(freeze_key) == "1"
        self._toggle_freeze_action.setChecked(freeze_active)
        self._toggle_freeze_action.setText(
            "Freeze Streak This Week (Active)" if freeze_active
            else "Freeze Streak This Week"
        )
        # Refresh vacation toggle.
        vac_active = self._db.get_setting("vacation_mode") == "1"
        self._toggle_vacation_action.setChecked(vac_active)
        # Refresh phone reminder toggle.
        phone_active = self._db.get_setting("phone_reminder_enabled") == "1"
        self._toggle_phone_reminder_action.setChecked(phone_active)
        # Keep the dashboard in sync if it's open.
        if self._dashboard is not None and self._dashboard.isVisible():
            self._dashboard.refresh()
