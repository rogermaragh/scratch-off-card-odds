# FAQ

### What does the value ratio actually mean?

It compares the prize money still unclaimed in a scratch-off game against what
that game held when it launched, per ticket. `1.21x` means the remaining
tickets carry 21% more prize money each than the average ticket did on day one,
because the good prizes have not been claimed yet.

It is not a prediction, and it does not make a game profitable. Scratch-offs
return roughly 60–75% of sales as prizes; a ratio above 1.00x means better than
that game's own starting point, not better than break-even.

### Is any of this guaranteed accurate?

No. ScratchOffCardOdds is unofficial. Numbers are read from public lottery sources and
can be stale, misparsed, or wrong. **Always check with your state lottery
before claiming anything.**

### Why does my state have results but no scratch-off rankings?

Ranking needs, for every prize tier, both the original number of prizes and the
number still unclaimed. Some states publish only "top prizes remaining", which
looks like the same thing and is not enough to compute anything. Pennsylvania
and Idaho are confirmed examples. Others simply do not have an adapter yet.

### Why does one state show no ticket price?

Because that state does not publish one anywhere. Maryland and Oklahoma are the
current cases. Those games still rank correctly — the ratio does not need the
price — but the return percentage is unavailable and the app leaves it blank
rather than guessing.

### Does the app track me?

No. There is no account, no analytics, and no third-party SDK. Location, if you
allow it, is converted to a state code on your device and the coordinates are
discarded. See `marketing/privacy.md`.

### Can I buy tickets in the app?

No, and that will not change. ScratchOffCardOdds displays information only.

### How often does the data update?

Draw results refresh twice daily. Scratch-off prize counts refresh weekly —
they change slowly, and reading them means driving a browser through several
hundred pages.

### Something is wrong. Where do I report it?

Open an issue with the state, the game, and what you expected. Scrapers break
when lottery sites change; that is the normal failure mode.
