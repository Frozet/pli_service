def get_areas(cursor, areaid=None):
    if areaid is None:
        cursor.execute("SELECT id, name, timestampdata FROM areas ORDER BY id")
    else:
        cursor.execute("SELECT id, name, timestampdata FROM areas WHERE id = %s", (areaid,))
    return cursor.fetchall()


def get_area(cursor, area_id):
    cursor.execute("SELECT id, name, timestampdata FROM areas WHERE id = %s", (area_id,))
    return cursor.fetchone()
