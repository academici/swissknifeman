def find(conn, identity):
    conn.execute('SELECT * FROM skm_planning.plans WHERE id = %s', (identity,))
