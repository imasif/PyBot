# database.py
import sqlite3
import json

DB_FILE = "MyPyBot.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # Table for messages
    c.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform TEXT,
            user_id TEXT,
            user_name TEXT,
            message TEXT,
            reply TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    # Table for configuration (key-value)
    c.execute('''
        CREATE TABLE IF NOT EXISTS config (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    # Table for cron jobs
    c.execute('''
        CREATE TABLE IF NOT EXISTS cron_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            job_type TEXT,
            schedule TEXT,
            params TEXT,
            enabled INTEGER DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    # Table for sleep tracking
    c.execute('''
        CREATE TABLE IF NOT EXISTS sleep_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            event_type TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            notes TEXT
        )
    ''')
    # Table for generic tracking (fitness, habits, mood, etc.)
    c.execute('''
        CREATE TABLE IF NOT EXISTS tracking_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            category TEXT,
            event_type TEXT,
            value REAL,
            unit TEXT,
            notes TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    # NOTE: Reminders are now handled by cron_jobs table (one-time scheduled jobs)
    # Table for notes/memos
    c.execute('''
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            title TEXT,
            content TEXT,
            tags TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    # Table for shopping lists
    c.execute('''
        CREATE TABLE IF NOT EXISTS shopping_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            item_name TEXT,
            quantity TEXT,
            is_purchased INTEGER DEFAULT 0,
            list_name TEXT DEFAULT 'default',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            purchased_at DATETIME
        )
    ''')
    # Table for timers
    c.execute('''
        CREATE TABLE IF NOT EXISTS timers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            name TEXT,
            duration_seconds INTEGER,
            started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            ends_at DATETIME,
            is_active INTEGER DEFAULT 1,
            is_completed INTEGER DEFAULT 0
        )
    ''')
    # Table for learned patterns (AI learning from successful interactions)
    c.execute('''
        CREATE TABLE IF NOT EXISTS learned_patterns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            pattern_type TEXT,
            user_input TEXT,
            detected_intent TEXT,
            confidence REAL DEFAULT 1.0,
            success_count INTEGER DEFAULT 1,
            last_used DATETIME DEFAULT CURRENT_TIMESTAMP,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    # Table for user preferences and context
    c.execute('''
        CREATE TABLE IF NOT EXISTS user_context (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            context_key TEXT,
            context_value TEXT,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def save_message(platform, user_id, user_name, message, reply):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        INSERT INTO messages (platform, user_id, user_name, message, reply)
        VALUES (?, ?, ?, ?, ?)
    ''', (platform, user_id, user_name, message, reply))
    conn.commit()
    conn.close()

def get_recent_messages(limit=20):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        SELECT platform, user_name, message, reply, timestamp
        FROM messages
        ORDER BY timestamp DESC
        LIMIT ?
    ''', (limit,))
    rows = c.fetchall()
    conn.close()
    return rows

def get_message_count():
    """Get total count of messages in database"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM messages')
    count = c.fetchone()[0]
    conn.close()
    return count

def get_user_chat_history(user_id, limit=10):
    """Get recent chat history for a specific user"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        SELECT message, reply
        FROM messages
        WHERE user_id = ? AND platform = 'telegram'
        ORDER BY timestamp DESC
        LIMIT ?
    ''', (user_id, limit))
    rows = c.fetchall()
    conn.close()
    # Return in chronological order (oldest first)
    return list(reversed(rows))

def get_config(key, default=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT value FROM config WHERE key = ?', (key,))
    row = c.fetchone()
    conn.close()
    if row:
        return row[0]
    return default

def set_config(key, value):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        INSERT INTO config (key, value)
        VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value
    ''', (key, value))
    conn.commit()
    conn.close()

# ---------- Cron Job Functions ----------
def add_cron_job(name, job_type, schedule, params=None):
    """Add a new cron job"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    params_json = json.dumps(params) if params else "{}"
    try:
        c.execute('''
            INSERT INTO cron_jobs (name, job_type, schedule, params)
            VALUES (?, ?, ?, ?)
        ''', (name, job_type, schedule, params_json))
        conn.commit()
        conn.close()
        return True, "Job added successfully"
    except sqlite3.IntegrityError:
        conn.close()
        return False, "Job with this name already exists"

def get_all_cron_jobs():
    """Get all cron jobs"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT id, name, job_type, schedule, params, enabled FROM cron_jobs')
    rows = c.fetchall()
    conn.close()
    jobs = []
    for row in rows:
        jobs.append({
            'id': row[0],
            'name': row[1],
            'job_type': row[2],
            'schedule': row[3],
            'params': json.loads(row[4]) if row[4] else {},
            'enabled': bool(row[5])
        })
    return jobs

def remove_cron_job(name):
    """Remove a cron job by name"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('DELETE FROM cron_jobs WHERE name = ?', (name,))
    deleted = c.rowcount
    conn.commit()
    conn.close()
    return deleted > 0

def update_cron_job(name, schedule=None, params=None, enabled=None):
    """Update a cron job by name"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # Build update query dynamically based on what's provided
    updates = []
    values = []
    
    if schedule is not None:
        updates.append('schedule = ?')
        values.append(schedule)
    
    if params is not None:
        updates.append('params = ?')
        values.append(json.dumps(params))
    
    if enabled is not None:
        updates.append('enabled = ?')
        values.append(1 if enabled else 0)
    
    if not updates:
        conn.close()
        return False, "No updates provided"
    
    values.append(name)
    query = f"UPDATE cron_jobs SET {', '.join(updates)} WHERE name = ?"
    
    c.execute(query, values)
    updated = c.rowcount
    conn.commit()
    conn.close()
    
    return updated > 0, "Job updated successfully" if updated > 0 else "Job not found"

def get_cron_job_by_name(name):
    """Get a specific cron job by name"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        SELECT id, name, job_type, schedule, params, enabled
        FROM cron_jobs
        WHERE name = ?
    ''', (name,))
    row = c.fetchone()
    conn.close()
    
    if row:
        return {
            'id': row[0],
            'name': row[1],
            'job_type': row[2],
            'schedule': row[3],
            'params': json.loads(row[4]) if row[4] else {},
            'enabled': bool(row[5])
        }
    return None

def toggle_cron_job(name, enabled):
    """Enable or disable a cron job"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('UPDATE cron_jobs SET enabled = ? WHERE name = ?', (1 if enabled else 0, name))
    updated = c.rowcount
    conn.commit()
    conn.close()
    return updated > 0

# ---------- Notes Functions ----------
def add_note(user_id, title, content, tags=None):
    """Add a new note"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    tags_str = json.dumps(tags) if tags else None
    c.execute('''
        INSERT INTO notes (user_id, title, content, tags)
        VALUES (?, ?, ?, ?)
    ''', (user_id, title, content, tags_str))
    conn.commit()
    note_id = c.lastrowid
    conn.close()
    return note_id

def get_notes(user_id, limit=20):
    """Get notes for a user"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        SELECT id, title, content, tags, created_at, updated_at
        FROM notes
        WHERE user_id = ?
        ORDER BY updated_at DESC
        LIMIT ?
    ''', (user_id, limit))
    rows = c.fetchall()
    conn.close()
    return rows

def search_notes(user_id, query):
    """Search notes by title or content"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    search_pattern = f'%{query}%'
    c.execute('''
        SELECT id, title, content, tags, created_at, updated_at
        FROM notes
        WHERE user_id = ? 
        AND (title LIKE ? OR content LIKE ?)
        ORDER BY updated_at DESC
        LIMIT 20
    ''', (user_id, search_pattern, search_pattern))
    rows = c.fetchall()
    conn.close()
    return rows

def update_note(note_id, title=None, content=None, tags=None):
    """Update a note"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    updates = []
    params = []
    
    if title is not None:
        updates.append('title = ?')
        params.append(title)
    if content is not None:
        updates.append('content = ?')
        params.append(content)
    if tags is not None:
        updates.append('tags = ?')
        params.append(json.dumps(tags))
    
    if updates:
        updates.append('updated_at = CURRENT_TIMESTAMP')
        params.append(note_id)
        query = f'UPDATE notes SET {", ".join(updates)} WHERE id = ?'
        c.execute(query, params)
        updated = c.rowcount
    else:
        updated = 0
    
    conn.commit()
    conn.close()
    return updated > 0

def delete_note(note_id):
    """Delete a note"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('DELETE FROM notes WHERE id = ?', (note_id,))
    deleted = c.rowcount
    conn.commit()
    conn.close()
    return deleted > 0

# ---------- Shopping List Functions ----------
def add_shopping_item(user_id, item_name, quantity=None, list_name='default'):
    """Add an item to shopping list"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        INSERT INTO shopping_items (user_id, item_name, quantity, list_name)
        VALUES (?, ?, ?, ?)
    ''', (user_id, item_name, quantity, list_name))
    conn.commit()
    item_id = c.lastrowid
    conn.close()
    return item_id

def get_shopping_list(user_id, list_name='default', include_purchased=False):
    """Get shopping list items"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    if include_purchased:
        c.execute('''
            SELECT id, item_name, quantity, is_purchased, created_at
            FROM shopping_items
            WHERE user_id = ? AND list_name = ?
            ORDER BY is_purchased ASC, created_at DESC
        ''', (user_id, list_name))
    else:
        c.execute('''
            SELECT id, item_name, quantity, is_purchased, created_at
            FROM shopping_items
            WHERE user_id = ? AND list_name = ? AND is_purchased = 0
            ORDER BY created_at DESC
        ''', (user_id, list_name))
    rows = c.fetchall()
    conn.close()
    return rows

def mark_item_purchased(item_id):
    """Mark an item as purchased"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        UPDATE shopping_items
        SET is_purchased = 1, purchased_at = CURRENT_TIMESTAMP
        WHERE id = ?
    ''', (item_id,))
    updated = c.rowcount
    conn.commit()
    conn.close()
    return updated > 0

def delete_shopping_item(item_id):
    """Delete a shopping item"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('DELETE FROM shopping_items WHERE id = ?', (item_id,))
    deleted = c.rowcount
    conn.commit()
    conn.close()
    return deleted > 0

def clear_purchased_items(user_id, list_name='default'):
    """Clear all purchased items from a list"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        DELETE FROM shopping_items
        WHERE user_id = ? AND list_name = ? AND is_purchased = 1
    ''', (user_id, list_name))
    deleted = c.rowcount
    conn.commit()
    conn.close()
    return deleted

# ---------- Timer Functions ----------
def add_timer(user_id, name, duration_seconds):
    """Add a new timer"""
    from datetime import datetime, timedelta
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    ends_at = datetime.now() + timedelta(seconds=duration_seconds)
    c.execute('''
        INSERT INTO timers (user_id, name, duration_seconds, ends_at)
        VALUES (?, ?, ?, ?)
    ''', (user_id, name, duration_seconds, ends_at.isoformat()))
    conn.commit()
    timer_id = c.lastrowid
    conn.close()
    return timer_id

def get_active_timers(user_id):
    """Get active timers for a user"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        SELECT id, name, duration_seconds, started_at, ends_at
        FROM timers
        WHERE user_id = ? AND is_active = 1 AND is_completed = 0
        ORDER BY ends_at ASC
    ''', (user_id,))
    rows = c.fetchall()
    conn.close()
    return rows

def complete_timer(timer_id):
    """Mark a timer as completed"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        UPDATE timers
        SET is_completed = 1, is_active = 0
        WHERE id = ?
    ''', (timer_id,))
    updated = c.rowcount
    conn.commit()
    conn.close()
    return updated > 0

def cancel_timer(timer_id):
    """Cancel a timer"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        UPDATE timers
        SET is_active = 0
        WHERE id = ?
    ''', (timer_id,))
    updated = c.rowcount
    conn.commit()
    conn.close()
    return updated > 0

def log_sleep_event(user_id, event_type, notes=None):
    """Log a sleep event (bedtime or wake)"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        INSERT INTO sleep_logs (user_id, event_type, notes)
        VALUES (?, ?, ?)
    ''', (user_id, event_type, notes))
    conn.commit()
    conn.close()

def get_sleep_data(user_id, days=7):
    """Get sleep data for a user for the last N days"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        SELECT event_type, timestamp, notes
        FROM sleep_logs
        WHERE user_id = ?
        AND timestamp >= datetime('now', '-' || ? || ' days')
        ORDER BY timestamp ASC
    ''', (user_id, days))
    rows = c.fetchall()
    conn.close()
    return rows


def log_tracking_event(user_id, category, event_type, value=None, unit=None, notes=None):
    """Log a generic tracking event (exercise, study, mood, habits, etc.)"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        INSERT INTO tracking_logs (user_id, category, event_type, value, unit, notes)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (user_id, category, event_type, value, unit, notes))
    conn.commit()
    conn.close()

def get_tracking_data(user_id, category=None, days=30):
    """Get tracking data for a user, optionally filtered by category"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    if category:
        c.execute('''
            SELECT category, event_type, value, unit, notes, timestamp
            FROM tracking_logs
            WHERE user_id = ? AND category = ?
            AND timestamp >= datetime('now', '-' || ? || ' days')
            ORDER BY timestamp ASC
        ''', (user_id, category, days))
    else:
        c.execute('''
            SELECT category, event_type, value, unit, notes, timestamp
            FROM tracking_logs
            WHERE user_id = ?
            AND timestamp >= datetime('now', '-' || ? || ' days')
            ORDER BY timestamp ASC
        ''', (user_id, days))
    rows = c.fetchall()
    conn.close()
    return rows

def get_tracking_categories(user_id):
    """Get all tracking categories for a user"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        SELECT DISTINCT category
        FROM tracking_logs
        WHERE user_id = ?
        ORDER BY category
    ''', (user_id,))
    rows = c.fetchall()
    conn.close()
    return [row[0] for row in rows]
def get_all_sleep_data(user_id):
    """Get all sleep data for a user"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        SELECT event_type, timestamp, notes
        FROM sleep_logs
        WHERE user_id = ?
        ORDER BY timestamp ASC
    ''', (user_id,))
    rows = c.fetchall()
    conn.close()
    return rows

def toggle_cron_job(name, enabled):
    """Enable or disable a cron job"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('UPDATE cron_jobs SET enabled = ? WHERE name = ?', (1 if enabled else 0, name))
    updated = c.rowcount
    conn.commit()
    conn.close()
    return updated > 0

# ---------- Learning & Pattern Recognition ----------
def save_learned_pattern(user_id, pattern_type, user_input, detected_intent, confidence=1.0):
    """Save a successful pattern for future learning"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # Check if pattern already exists
    c.execute('''
        SELECT id, success_count FROM learned_patterns
        WHERE user_id = ? AND pattern_type = ? AND user_input = ? AND detected_intent = ?
    ''', (user_id, pattern_type, user_input.lower(), detected_intent))
    
    existing = c.fetchone()
    
    if existing:
        # Update success count and last_used
        c.execute('''
            UPDATE learned_patterns
            SET success_count = success_count + 1,
                last_used = CURRENT_TIMESTAMP,
                confidence = MIN(1.0, confidence + 0.1)
            WHERE id = ?
        ''', (existing[0],))
    else:
        # Insert new pattern
        c.execute('''
            INSERT INTO learned_patterns (user_id, pattern_type, user_input, detected_intent, confidence)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, pattern_type, user_input.lower(), detected_intent, confidence))
    
    conn.commit()
    conn.close()

def get_learned_patterns(user_id, pattern_type=None, min_confidence=0.5):
    """Get learned patterns for a user"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    base_query = '''
        SELECT id, pattern_type, user_input, detected_intent, confidence, success_count
        FROM learned_patterns
        WHERE user_id = ? AND confidence >= ?
    '''

    params = [user_id, min_confidence]

    if pattern_type:
        base_query += ' AND pattern_type = ?'
        params.append(pattern_type)

    base_query += ' ORDER BY pattern_type ASC, success_count DESC, confidence DESC'

    limit = 50 if pattern_type else 100
    base_query += ' LIMIT ?'
    params.append(limit)

    c.execute(base_query, tuple(params))
    rows = c.fetchall()
    conn.close()
    return rows

def clear_learned_patterns(user_id, pattern_type=None):
    """Clear learned patterns for a user (optionally by type)"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    if pattern_type:
        c.execute('DELETE FROM learned_patterns WHERE user_id = ? AND pattern_type = ?', (user_id, pattern_type))
    else:
        c.execute('DELETE FROM learned_patterns WHERE user_id = ?', (user_id,))
    
    deleted_count = c.rowcount
    conn.commit()
    conn.close()
    return deleted_count

def delete_learned_pattern(user_id, pattern_id):
    """Delete a single learned pattern entry"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('DELETE FROM learned_patterns WHERE user_id = ? AND id = ?', (user_id, pattern_id))
    deleted = c.rowcount
    conn.commit()
    conn.close()
    return deleted > 0

def save_user_context(user_id, context_key, context_value):
    """Save user-specific context/preferences"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    c.execute('''
        INSERT OR REPLACE INTO user_context (user_id, context_key, context_value, updated_at)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
    ''', (user_id, context_key, context_value))
    
    conn.commit()
    conn.close()

def get_user_context(user_id, context_key=None):
    """Get user context/preferences"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    if context_key:
        c.execute('''
            SELECT context_value FROM user_context
            WHERE user_id = ? AND context_key = ?
        ''', (user_id, context_key))
        row = c.fetchone()
        conn.close()
        return row[0] if row else None
    else:
        c.execute('''
            SELECT context_key, context_value FROM user_context
            WHERE user_id = ?
        ''', (user_id,))
        rows = c.fetchall()
        conn.close()
        return {row[0]: row[1] for row in rows}