from yams.bt_scanner import bleak_scan, collection_ctl, device_info
import asyncio

if __name__ == '__main__':
    asyncio.run(bleak_scan("MSense"))
    collection_ctl(device_info.keys(), False)

    print("All devices stop")