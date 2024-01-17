users = 8
paginate = 7


max_page = users // paginate
if users % paginate != 0:
    max_page += 1
print(f'max_page: {max_page} {users % paginate}')
for page in range(-1, 15):

    page = page % max_page
    start = page * paginate
    # print(f'start: {start}. page: {page}')
    end = start + paginate
    print(f'page: {page}. {start} - {end-1}')

