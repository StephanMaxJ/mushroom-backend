@app.get("/admin/users")
async def get_all_users(current_user: dict = Depends(get_current_user)):
    if current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    conn = get_database_connection()
    cursor = conn.cursor()
    
    # Get users with journal count
    if DATABASE_URL.startswith("postgresql://") or DATABASE_URL.startswith("postgres://"):
        cursor.execute('''
            SELECT u.id, u.username, u.email, u.full_name, u.role, u.is_active, u.created_at,
                   COUNT(j.id) as journal_count
            FROM users u
            LEFT JOIN journal_entries j ON u.id = j.user_id
            GROUP BY u.id, u.username, u.email, u.full_name, u.role, u.is_active, u.created_at
            ORDER BY u.created_at DESC
        ''')
    else:
        cursor.execute('''
            SELECT u.id, u.username, u.email, u.full_name, u.role, u.is_active, u.created_at,
                   COUNT(j.id) as journal_count
            FROM users u
            LEFT JOIN journal_entries j ON u.id = j.user_id
            GROUP BY u.id, u.username, u.email, u.full_name, u.role, u.is_active, u.created_at
            ORDER BY u.created_at DESC
        ''')
    
    users = cursor.fetchall()
    conn.close()
    
    return [
        {
            "id": user[0],
            "username": user[1],
            "email": user[2],
            "full_name": user[3],
            "role": user[4],
            "is_active": user[5],
            "created_at": user[6],
            "journal_count": user[7]
        }
        for user in users
    ]
