try:
    from yams.__main__ import main
    main()
except Exception as e:
    print(f"An error occurred: {e}")

input("Press Enter to exit...")