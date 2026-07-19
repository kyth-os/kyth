
# __KYTH_GENERATED_IMPORTS__
from .theme_base import BASE_QSS
from .theme_hub_overlay import HUB_OVERLAY_QSS
from .theme_home_polish import HOME_POLISH_QSS
from .theme_genz import GENZ_QSS


# KythOS theme: slate-blue surfaces, blue accent focus, restrained status colors.
# Palette:
#   window      #0c0e16      sidebar          #12141f
#   card        #151722      card hover       #1f2335
#   border      #26293a      strong border    #2e324c
#   input       #181b28      log/console      #1a1a1a
#   text        #ffffff      secondary text   #a6a6a6
#   accent      #4f8cff      accent (light)   #8fb8ff
#   ok #10b981   warn #f59e0b   error #ff99a4   danger button #c42b1c
#
# Passes are concatenated in application order — each later pass overrides
# selectors from the ones before it via normal QSS cascade rules, so the
# order here must match theme_base -> theme_hub_overlay -> theme_home_polish
# -> theme_genz.
QSS = BASE_QSS + HUB_OVERLAY_QSS + HOME_POLISH_QSS + GENZ_QSS
