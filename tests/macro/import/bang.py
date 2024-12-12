# coding: magic.macro

# imports non-macros in the context of the macro preprocessor

import! token as t
import! token

from! token import DEDENT as D
from! token import INDENT

from! token import! NAME as ID
from! token import! OP

from token import! NL as N
from token import! NEWLINE

from! .macro.foo import FOO
