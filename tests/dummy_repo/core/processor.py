def process_data(data, mode, flag, count, options):
    if mode == "a":
        if flag:
            if count > 10:
                if options.get("debug"):
                    print("Debug mode")
                    print("Processing...")
                    for i in range(count):
                        print(f"Item {i}")
            elif count > 5:
                if options.get("verbose"):
                    print("Verbose processing")
                    for i in range(count):
                        print(f"Item {i}")
                else:
                    print("Silent processing")
        else:
            if count > 10:
                for i in range(count):
                    print(f"Item {i}")
            elif count > 0:
                print("Processing")
            else:
                raise ValueError("Count must be positive")
    elif mode == "b":
        if flag:
            print("Mode B with flag")
        else:
            print("Mode B without flag")
            if count > 0:
                for i in range(count):
                    print(f"Item {i}")
    elif mode == "c":
        if options.get("fast"):
            print("Fast mode")
        elif options.get("safe"):
            print("Safe mode")
        else:
            print("Default mode C")
            for i in range(count):
                for j in range(count):
                    print(f"{i}.{j}")
    else:
        print("Unknown mode")
    return True
