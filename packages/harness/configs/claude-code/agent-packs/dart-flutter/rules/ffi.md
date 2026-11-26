---
paths:
  - "lib/**/ffi/**"
  - "lib/**/native/**"
---

FFI / native border (POS-peripherals):

- Memory pairing: `malloc`/`calloc` ↔ `free` on all paths, including erroneous ones.
- Check the return code of each native call; non-zero → diagnostic exception.
- Native calls - out UI-isolate (`Isolate.run`/isolated thread); path to `.so` not
  is hardcoded for one architecture; `DynamicLibrary.open()` in try/catch.
- Log peripheral return codes (fiscal officer/printer) into a separate channel.
