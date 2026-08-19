"""KythOS theme: slate-blue surfaces, blue accent focus, restrained status colors.

Was a 4-pass cascade (theme_base -> theme_hub_overlay -> theme_home_polish
-> theme_genz), each later pass silently overriding selectors from the ones
before it. That meant the source of truth for any given selector was
"whichever file happens to load last," which several theme_base docstrings
ended up documenting by hand ("kept here in sync ... rather than removed")
instead of ever actually being resolved. All four passes are folded into
theme_base's own per-concern files now — this is the only pass.
"""
from .theme_base import BASE_QSS

QSS = BASE_QSS
