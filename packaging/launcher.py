import multiprocessing
import sys


if __name__ == '__main__':
    multiprocessing.freeze_support()
    if len(sys.argv) > 1 and sys.argv[1] == '--check-installation':
        from check_installation import main
        sys.exit(main(sys.argv[2:]))

    from structura_edit.__main__ import main
    sys.exit(main())
