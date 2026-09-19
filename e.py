from mcub_engine import get_kernel
k = get_kernel()
if k:
    print("=== COMMAND HANDLERS ===")
    for cmd, handler in k.command_handlers.items():
        print(f"  .{cmd} -> {handler.__name__ if hasattr(handler, '__name__') else handler}")
    print(f"\nTotal commands: {len(k.command_handlers)}")
    print(f"\n=== INLINE HANDLERS ===")
    for name in k._inline_handlers:
        print(f"  .iq {name}")
else:
    print("❌ Kernel is None!")
