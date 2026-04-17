from utils.blum import Blum
from contextlib import suppress
import asyncio
import os

async def main():
    data_file = 'data.txt'
    if not os.path.exists(data_file):
        print('data.txt not found!')
        return
    datas = [line.strip() for line in open(data_file).readlines() if line.strip()]
    if not datas:
        print('0 accounts in data.txt')
        return
    print(f'Total accounts: {len(datas)}')
    tasks = []
    for thread, init_data in enumerate(datas):
        tasks.append(asyncio.create_task(Blum(init_data=init_data, thread=thread).main()))
    await asyncio.gather(*tasks)

if __name__ == '__main__':
    with suppress(KeyboardInterrupt, RuntimeError, RuntimeWarning):
        asyncio.run(main())
