def preprocess(data: str):
    return f'''
import cppyy

cppyy.cppdef(r"""{data}""")
from cppyy.gbl import main

if __name__ == "__main__":
    main()
'''
