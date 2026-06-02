import sqlite3
conn = sqlite3.connect('streamclipper.db')
conn.execute("UPDATE streamers SET platform='youtube', url='https://www.youtube.com/@ishowspeed' WHERE name='IShowSpeed'")
conn.execute("UPDATE streamers SET platform='kick', url='https://kick.com/adinross' WHERE name='Adin Ross'")
conn.commit()
conn.close()
print("Done")
