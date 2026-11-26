def find(conn, identity):
    conn.execute(f'SELECT * FROM skm_planning.plans WHERE id = {identity}')
