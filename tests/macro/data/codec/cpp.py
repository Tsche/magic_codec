# coding: magic.macro

@macro
def cpp(code):
    # print(code)
    import cppyy

    cppyy.cppdef(code.string)
    for name in dir(cppyy.gbl):
      if name.startswith('__') or name in ("std", "CppyyLegacy"): continue
      obj = getattr(cppyy.gbl, name)

      if callable(obj) and not isinstance(obj, type):
        code = _Code(f"""
def {name}(*args, **kwargs): 
  import cppyy
  return getattr(cppyy.gbl, "{name}")(*args, **kwargs)
""")
        yield code


cpp!:
  #include <string>
  struct Bar {
     int x;
     std::string y;
  };

  Bar foo() {
    return {42, "test"};
  }

bar_obj = foo()
print(bar_obj.x, bar_obj.y)