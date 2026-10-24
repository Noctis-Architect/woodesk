import sys


if __name__ == "__main__":
    if "--notification-worker" in sys.argv:
        from app.notifications.worker import main as notification_main

        sys.exit(notification_main())

    from app.main import main

    main()
