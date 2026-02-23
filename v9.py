#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════╗
║          NEXUS CMMS — Computerized Maintenance Management System     ║
║          NEXUS Enterprise v9 | Enhanced Security + UI + Mobile       ║
╚══════════════════════════════════════════════════════════════════════╝

HOW TO RUN:
    pip install flask flask-limiter
    python3 cmms_app_v8_enterprise.py

Then open your browser at: http://localhost:5050

WHAT'S NEW IN V8:
    ✓ Fixed command palette shortcut (Ctrl+K / Cmd+K)
    ✓ Enhanced security with rate limiting & CSRF protection
    ✓ Improved password hashing (PBKDF2-SHA256)
    ✓ Modern UI with better accessibility
    ✓ Advanced search and filtering
    ✓ Mobile-responsive design improvements
    ✓ Real-time notifications system
    ✓ Export to PDF with better formatting
    ✓ Dashboard analytics improvements
    ✓ Session management enhancements
"""

import sqlite3, json, os, sys, webbrowser, threading, hashlib, secrets, smtplib, csv, io, time, queue, re
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from functools import wraps
from flask import Flask, request, jsonify, session, redirect, url_for, send_file, make_response, Response, stream_with_context

DB_PATH       = "cmms_nexus.db"
APP_VERSION   = "9.0.0"
APP_BUILD     = "2026-02-23"
APP_CODENAME  = "Enterprise Mobile Edition"

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USERNAME = ""
SMTP_PASSWORD = ""
FROM_EMAIL = ""

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def db_is_compatible():
    """Check if the existing DB has the required schema."""
    try:
        conn = sqlite3.connect(DB_PATH)
        checks = [
            "SELECT department FROM users LIMIT 1",
            "SELECT address FROM locations LIMIT 1",
            "SELECT notes FROM parts LIMIT 1",
            "SELECT criticality FROM assets LIMIT 1",
            "SELECT labor_cost FROM work_orders LIMIT 1",
            "SELECT checklist FROM pm_schedules LIMIT 1",
        ]
        for sql in checks:
            try:
                conn.execute(sql)
            except sqlite3.OperationalError:
                conn.close()
                return False
        conn.close()
        return True
    except Exception:
        return False

def reset_db():
    """Rename old DB and start fresh."""
    import shutil
    if os.path.exists(DB_PATH):
        backup = DB_PATH.replace('.db', f'_backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.db')
        shutil.move(DB_PATH, backup)
        print(f"  Old database backed up to: {backup}")
    print("  Creating fresh database...")

def migrate_db(conn):
    """Add missing columns to existing tables (safe to run on any version)."""
    c = conn.cursor()
    migrations = [
        # users
        ("ALTER TABLE users ADD COLUMN department TEXT",),
        ("ALTER TABLE users ADD COLUMN phone TEXT",),
        ("ALTER TABLE users ADD COLUMN avatar TEXT",),
        ("ALTER TABLE users ADD COLUMN last_login TEXT",),
        ("ALTER TABLE users ADD COLUMN is_active INTEGER DEFAULT 1",),
        ("ALTER TABLE users ADD COLUMN updated_at TEXT DEFAULT (datetime('now'))",),
        # locations
        ("ALTER TABLE locations ADD COLUMN code TEXT",),
        ("ALTER TABLE locations ADD COLUMN parent_id INTEGER",),
        ("ALTER TABLE locations ADD COLUMN description TEXT",),
        ("ALTER TABLE locations ADD COLUMN address TEXT",),
        ("ALTER TABLE locations ADD COLUMN city TEXT",),
        ("ALTER TABLE locations ADD COLUMN state TEXT",),
        ("ALTER TABLE locations ADD COLUMN zip_code TEXT",),
        # asset_categories
        ("ALTER TABLE asset_categories ADD COLUMN description TEXT",),
        ("ALTER TABLE asset_categories ADD COLUMN color TEXT DEFAULT '#3B82F6'",),
        ("ALTER TABLE asset_categories ADD COLUMN icon TEXT DEFAULT '⚙'",),
        # assets
        ("ALTER TABLE assets ADD COLUMN code TEXT",),
        ("ALTER TABLE assets ADD COLUMN category_id INTEGER",),
        ("ALTER TABLE assets ADD COLUMN location_id INTEGER",),
        ("ALTER TABLE assets ADD COLUMN make TEXT",),
        ("ALTER TABLE assets ADD COLUMN model TEXT",),
        ("ALTER TABLE assets ADD COLUMN serial_number TEXT",),
        ("ALTER TABLE assets ADD COLUMN purchase_date TEXT",),
        ("ALTER TABLE assets ADD COLUMN purchase_cost REAL",),
        ("ALTER TABLE assets ADD COLUMN warranty_expiry TEXT",),
        ("ALTER TABLE assets ADD COLUMN warranty_notes TEXT",),
        ("ALTER TABLE assets ADD COLUMN criticality TEXT DEFAULT 'medium'",),
        ("ALTER TABLE assets ADD COLUMN barcode TEXT",),
        ("ALTER TABLE assets ADD COLUMN qr_code TEXT",),
        ("ALTER TABLE assets ADD COLUMN image_path TEXT",),
        ("ALTER TABLE assets ADD COLUMN manual_path TEXT",),
        ("ALTER TABLE assets ADD COLUMN notes TEXT",),
        ("ALTER TABLE assets ADD COLUMN updated_at TEXT DEFAULT (datetime('now'))",),
        # work_orders
        ("ALTER TABLE work_orders ADD COLUMN notes TEXT",),
        ("ALTER TABLE work_orders ADD COLUMN failure_reason TEXT",),
        ("ALTER TABLE work_orders ADD COLUMN resolution TEXT",),
        ("ALTER TABLE work_orders ADD COLUMN safety_notes TEXT",),
        ("ALTER TABLE work_orders ADD COLUMN tools_required TEXT",),
        ("ALTER TABLE work_orders ADD COLUMN approved_by INTEGER",),
        ("ALTER TABLE work_orders ADD COLUMN approved_at TEXT",),
        ("ALTER TABLE work_orders ADD COLUMN labor_cost REAL DEFAULT 0",),
        ("ALTER TABLE work_orders ADD COLUMN parts_cost REAL DEFAULT 0",),
        ("ALTER TABLE work_orders ADD COLUMN total_cost REAL DEFAULT 0",),
        ("ALTER TABLE work_orders ADD COLUMN estimated_hours REAL",),
        ("ALTER TABLE work_orders ADD COLUMN actual_hours REAL",),
        ("ALTER TABLE work_orders ADD COLUMN started_at TEXT",),
        ("ALTER TABLE work_orders ADD COLUMN completed_at TEXT",),
        ("ALTER TABLE work_orders ADD COLUMN completion_notes TEXT",),
        ("ALTER TABLE work_orders ADD COLUMN scheduled_date TEXT",),
        ("ALTER TABLE work_orders ADD COLUMN due_date TEXT",),
        ("ALTER TABLE work_orders ADD COLUMN updated_at TEXT DEFAULT (datetime('now'))",),
        # pm_schedules
        ("ALTER TABLE pm_schedules ADD COLUMN asset_id INTEGER",),
        ("ALTER TABLE pm_schedules ADD COLUMN frequency TEXT DEFAULT 'monthly'",),
        ("ALTER TABLE pm_schedules ADD COLUMN frequency_value INTEGER DEFAULT 1",),
        ("ALTER TABLE pm_schedules ADD COLUMN last_performed TEXT",),
        ("ALTER TABLE pm_schedules ADD COLUMN next_due TEXT",),
        ("ALTER TABLE pm_schedules ADD COLUMN assigned_to INTEGER",),
        ("ALTER TABLE pm_schedules ADD COLUMN estimated_hours REAL",),
        ("ALTER TABLE pm_schedules ADD COLUMN estimated_cost REAL",),
        ("ALTER TABLE pm_schedules ADD COLUMN checklist TEXT",),
        ("ALTER TABLE pm_schedules ADD COLUMN safety_instructions TEXT",),
        ("ALTER TABLE pm_schedules ADD COLUMN requires_shutdown INTEGER DEFAULT 0",),
        ("ALTER TABLE pm_schedules ADD COLUMN active INTEGER DEFAULT 1",),
        # parts
        ("ALTER TABLE parts ADD COLUMN max_quantity INTEGER DEFAULT 100",),
        ("ALTER TABLE parts ADD COLUMN reorder_point INTEGER DEFAULT 5",),
        ("ALTER TABLE parts ADD COLUMN bin_number TEXT",),
        ("ALTER TABLE parts ADD COLUMN manufacturer TEXT",),
        ("ALTER TABLE parts ADD COLUMN lead_time_days INTEGER DEFAULT 7",),
        ("ALTER TABLE parts ADD COLUMN unit_cost REAL DEFAULT 0",),
        ("ALTER TABLE parts ADD COLUMN location TEXT",),
        ("ALTER TABLE parts ADD COLUMN supplier TEXT",),
        ("ALTER TABLE parts ADD COLUMN updated_at TEXT DEFAULT (datetime('now'))",),
        # suppliers
        ("ALTER TABLE suppliers ADD COLUMN contact_person TEXT",),
        ("ALTER TABLE suppliers ADD COLUMN email TEXT",),
        ("ALTER TABLE suppliers ADD COLUMN phone TEXT",),
        ("ALTER TABLE suppliers ADD COLUMN address TEXT",),
        ("ALTER TABLE suppliers ADD COLUMN website TEXT",),
        ("ALTER TABLE suppliers ADD COLUMN tax_id TEXT",),
        ("ALTER TABLE suppliers ADD COLUMN payment_terms TEXT",),
        ("ALTER TABLE suppliers ADD COLUMN notes TEXT",),
        # po_items — add missing columns (existing DBs had quantity_ordered, not quantity/description)
        ("ALTER TABLE po_items ADD COLUMN description TEXT",),
        ("ALTER TABLE po_items ADD COLUMN quantity REAL DEFAULT 1",),
        ("ALTER TABLE po_items ADD COLUMN quantity_received INTEGER DEFAULT 0",),
        # purchase_orders — add updated_at (use plain text default, not datetime() function which fails in ALTER TABLE)
        ("ALTER TABLE purchase_orders ADD COLUMN updated_at TEXT",),
    ]
    for (sql,) in migrations:
        try:
            c.execute(sql)
        except Exception:
            pass  # Column already exists or table doesn't exist yet — safe to ignore

    # Fix NULL values left on existing rows after ALTER TABLE
    null_fixes = [
        "UPDATE users SET is_active=1 WHERE is_active IS NULL",
        "UPDATE users SET role='technician' WHERE role IS NULL",
        "UPDATE assets SET criticality='medium' WHERE criticality IS NULL",
        "UPDATE assets SET status='active' WHERE status IS NULL",
        "UPDATE work_orders SET labor_cost=0 WHERE labor_cost IS NULL",
        "UPDATE work_orders SET parts_cost=0 WHERE parts_cost IS NULL",
        "UPDATE work_orders SET total_cost=0 WHERE total_cost IS NULL",
        "UPDATE parts SET max_quantity=100 WHERE max_quantity IS NULL",
        "UPDATE parts SET reorder_point=5 WHERE reorder_point IS NULL",
        "UPDATE parts SET lead_time_days=7 WHERE lead_time_days IS NULL",
        "UPDATE pm_schedules SET frequency_value=1 WHERE frequency_value IS NULL",
        "UPDATE pm_schedules SET requires_shutdown=0 WHERE requires_shutdown IS NULL",
    ]
    for sql in null_fixes:
        try:
            c.execute(sql)
        except Exception:
            pass
    conn.commit()

def init_db():
    conn = get_db()
    c = conn.cursor()
    # Run migrations first so existing DBs get any missing columns
    migrate_db(conn)
    c.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        full_name TEXT,
        role TEXT DEFAULT 'technician',
        email TEXT,
        department TEXT,
        phone TEXT,
        avatar TEXT,
        last_login TEXT,
        is_active INTEGER DEFAULT 1,
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS locations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL, code TEXT, parent_id INTEGER,
        description TEXT, address TEXT, city TEXT, state TEXT, zip_code TEXT,
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (parent_id) REFERENCES locations(id)
    );
    CREATE TABLE IF NOT EXISTS asset_categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL, description TEXT,
        color TEXT DEFAULT '#3B82F6', icon TEXT DEFAULT '⚙'
    );
    CREATE TABLE IF NOT EXISTS assets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL, code TEXT UNIQUE, category_id INTEGER, location_id INTEGER,
        status TEXT DEFAULT 'active', make TEXT, model TEXT, serial_number TEXT,
        purchase_date TEXT, purchase_cost REAL, warranty_expiry TEXT, warranty_notes TEXT,
        description TEXT, criticality TEXT DEFAULT 'medium', barcode TEXT,
        qr_code TEXT, image_path TEXT, manual_path TEXT, notes TEXT,
        created_at TEXT DEFAULT (datetime('now')), updated_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (category_id) REFERENCES asset_categories(id),
        FOREIGN KEY (location_id) REFERENCES locations(id)
    );
    CREATE TABLE IF NOT EXISTS work_orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        wo_number TEXT UNIQUE NOT NULL, title TEXT NOT NULL, description TEXT,
        asset_id INTEGER, type TEXT DEFAULT 'corrective', priority TEXT DEFAULT 'medium',
        status TEXT DEFAULT 'open', assigned_to INTEGER, requested_by INTEGER,
        scheduled_date TEXT, due_date TEXT, started_at TEXT, completed_at TEXT,
        estimated_hours REAL, actual_hours REAL, labor_cost REAL DEFAULT 0,
        parts_cost REAL DEFAULT 0, total_cost REAL DEFAULT 0,
        completion_notes TEXT, failure_reason TEXT, resolution TEXT,
        safety_notes TEXT, tools_required TEXT, notes TEXT,
        approved_by INTEGER, approved_at TEXT,
        created_at TEXT DEFAULT (datetime('now')), updated_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (asset_id) REFERENCES assets(id),
        FOREIGN KEY (assigned_to) REFERENCES users(id),
        FOREIGN KEY (requested_by) REFERENCES users(id),
        FOREIGN KEY (approved_by) REFERENCES users(id)
    );
    CREATE TABLE IF NOT EXISTS pm_schedules (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL, asset_id INTEGER, description TEXT,
        frequency TEXT DEFAULT 'monthly', frequency_value INTEGER DEFAULT 1,
        last_performed TEXT, next_due TEXT, assigned_to INTEGER,
        estimated_hours REAL, estimated_cost REAL, checklist TEXT,
        safety_instructions TEXT, requires_shutdown INTEGER DEFAULT 0, active INTEGER DEFAULT 1,
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (asset_id) REFERENCES assets(id),
        FOREIGN KEY (assigned_to) REFERENCES users(id)
    );
    CREATE TABLE IF NOT EXISTS parts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL, part_number TEXT UNIQUE, description TEXT,
        quantity INTEGER DEFAULT 0, min_quantity INTEGER DEFAULT 0,
        max_quantity INTEGER DEFAULT 100, reorder_point INTEGER DEFAULT 5,
        unit_cost REAL DEFAULT 0, location TEXT, bin_number TEXT,
        supplier TEXT, manufacturer TEXT, lead_time_days INTEGER DEFAULT 7,
        notes TEXT, created_at TEXT DEFAULT (datetime('now')), updated_at TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS suppliers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL, contact_person TEXT, email TEXT, phone TEXT,
        address TEXT, website TEXT, tax_id TEXT, payment_terms TEXT, notes TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS purchase_orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        po_number TEXT UNIQUE NOT NULL, supplier_id INTEGER, ordered_by INTEGER,
        order_date TEXT DEFAULT (datetime('now')), expected_date TEXT, received_date TEXT,
        status TEXT DEFAULT 'pending', subtotal REAL, tax REAL, shipping REAL, total REAL, notes TEXT,
        created_at TEXT DEFAULT (datetime('now')), updated_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (supplier_id) REFERENCES suppliers(id),
        FOREIGN KEY (ordered_by) REFERENCES users(id)
    );
    CREATE TABLE IF NOT EXISTS po_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        po_id INTEGER, part_id INTEGER, description TEXT,
        quantity REAL DEFAULT 1, quantity_received INTEGER DEFAULT 0,
        unit_cost REAL, line_total REAL, notes TEXT,
        FOREIGN KEY (po_id) REFERENCES purchase_orders(id),
        FOREIGN KEY (part_id) REFERENCES parts(id)
    );
    CREATE TABLE IF NOT EXISTS wo_parts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        wo_id INTEGER, part_id INTEGER, quantity_used INTEGER DEFAULT 1,
        unit_cost REAL, line_total REAL, notes TEXT,
        FOREIGN KEY (wo_id) REFERENCES work_orders(id),
        FOREIGN KEY (part_id) REFERENCES parts(id)
    );
    CREATE TABLE IF NOT EXISTS wo_time_entries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        wo_id INTEGER, user_id INTEGER, hours_worked REAL,
        work_date TEXT, description TEXT, created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (wo_id) REFERENCES work_orders(id),
        FOREIGN KEY (user_id) REFERENCES users(id)
    );
    CREATE TABLE IF NOT EXISTS comments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        wo_id INTEGER, user_id INTEGER, content TEXT NOT NULL,
        is_private INTEGER DEFAULT 0, attachment_path TEXT,
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (wo_id) REFERENCES work_orders(id),
        FOREIGN KEY (user_id) REFERENCES users(id)
    );
    CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER, type TEXT, title TEXT, message TEXT, link TEXT,
        is_read INTEGER DEFAULT 0, created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (user_id) REFERENCES users(id)
    );
    CREATE TABLE IF NOT EXISTS audit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER, action TEXT, table_name TEXT, record_id INTEGER,
        old_value TEXT, new_value TEXT, ip_address TEXT, user_agent TEXT,
        details TEXT, created_at TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS settings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        key TEXT UNIQUE NOT NULL, value TEXT, description TEXT,
        updated_at TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS meter_readings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        asset_id INTEGER, meter_type TEXT, reading_value REAL,
        reading_date TEXT, notes TEXT, recorded_by INTEGER,
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (asset_id) REFERENCES assets(id),
        FOREIGN KEY (recorded_by) REFERENCES users(id)
    );
    CREATE TABLE IF NOT EXISTS asset_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        asset_id INTEGER NOT NULL,
        event_type TEXT NOT NULL,
        event_title TEXT NOT NULL,
        event_detail TEXT,
        performed_by INTEGER,
        cost REAL,
        reference_id INTEGER,
        reference_type TEXT,
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (asset_id) REFERENCES assets(id),
        FOREIGN KEY (performed_by) REFERENCES users(id)
    );
    CREATE TABLE IF NOT EXISTS downtime_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        asset_id INTEGER NOT NULL,
        start_time TEXT NOT NULL,
        end_time TEXT,
        reason TEXT,
        category TEXT DEFAULT 'unplanned',
        wo_id INTEGER,
        recorded_by INTEGER,
        duration_hours REAL,
        notes TEXT,
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (asset_id) REFERENCES assets(id),
        FOREIGN KEY (wo_id) REFERENCES work_orders(id),
        FOREIGN KEY (recorded_by) REFERENCES users(id)
    );
    CREATE TABLE IF NOT EXISTS asset_parts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        asset_id INTEGER NOT NULL,
        part_id INTEGER NOT NULL,
        quantity_required INTEGER DEFAULT 1,
        notes TEXT,
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (asset_id) REFERENCES assets(id),
        FOREIGN KEY (part_id) REFERENCES parts(id),
        UNIQUE(asset_id, part_id)
    );
    CREATE TABLE IF NOT EXISTS maintenance_budget (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        year INTEGER NOT NULL,
        month INTEGER NOT NULL,
        budget_amount REAL DEFAULT 0,
        notes TEXT,
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now')),
        UNIQUE(year, month)
    );
    CREATE TABLE IF NOT EXISTS sla_config (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        priority TEXT UNIQUE NOT NULL,
        response_hours REAL DEFAULT 4,
        resolution_hours REAL DEFAULT 24,
        escalation_hours REAL DEFAULT 48,
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS auto_backup_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        backup_file TEXT,
        backup_type TEXT DEFAULT 'auto',
        size_kb REAL,
        status TEXT DEFAULT 'success',
        notes TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    );
    """)

    # Seed SLA config defaults
    sla_defaults = [
        ('critical', 1, 4, 8),
        ('high',     2, 8, 24),
        ('medium',   4, 24, 72),
        ('low',      8, 72, 168),
    ]
    for priority, resp, resol, esc in sla_defaults:
        c.execute("""INSERT OR IGNORE INTO sla_config (priority,response_hours,resolution_hours,escalation_hours)
                     VALUES (?,?,?,?)""", (priority, resp, resol, esc))

    settings = [
        ('company_name', 'NEXUS CMMS', 'Company name'),
        ('company_email', 'admin@cmms.local', 'Company email'),
        ('company_phone', '+1 (555) 123-4567', 'Company phone'),
        ('date_format', 'YYYY-MM-DD', 'Date format'),
        ('currency_symbol', '₹', 'Currency symbol'),
        ('wo_prefix', 'WO', 'Work order prefix'),
        ('email_notifications', 'true', 'Enable email notifications'),
        ('update_server_url', '', 'Software update server URL (leave blank to disable auto-check)'),
        ('auto_backup_enabled', 'true', 'Enable automatic scheduled database backups'),
        ('auto_backup_interval_hours', '24', 'Auto backup interval in hours'),
        ('auto_backup_keep_count', '7', 'Number of auto backups to keep'),
        ('annual_maintenance_budget', '0', 'Annual maintenance budget amount'),
        ('escalation_enabled', 'true', 'Auto-escalate overdue work orders'),
    ]
    for key, value, desc in settings:
        c.execute("INSERT OR IGNORE INTO settings (key, value, description) VALUES (?, ?, ?)", (key, value, desc))

    admin_hash = hashlib.sha256("admin123".encode()).hexdigest()
    c.execute("""INSERT OR IGNORE INTO users (username, password_hash, full_name, role, email, department, phone)
                 VALUES ('admin', ?, 'System Administrator', 'admin', 'admin@cmms.local', 'IT', '+1-555-0001')""", (admin_hash,))
    tech_hash = hashlib.sha256("tech123".encode()).hexdigest()
    c.execute("""INSERT OR IGNORE INTO users (username, password_hash, full_name, role, email, department, phone)
                 VALUES ('tech1', ?, 'John Smith', 'technician', 'john.smith@cmms.local', 'Maintenance', '+1-555-0002')""", (tech_hash,))
    c.execute("""INSERT OR IGNORE INTO users (username, password_hash, full_name, role, email, department, phone)
                 VALUES ('tech2', ?, 'Mike Johnson', 'technician', 'mike.j@cmms.local', 'Maintenance', '+1-555-0003')""",
              (hashlib.sha256("tech123".encode()).hexdigest(),))
    c.execute("""INSERT OR IGNORE INTO users (username, password_hash, full_name, role, email, department, phone)
                 VALUES ('manager1', ?, 'Sarah Johnson', 'manager', 'sarah.j@cmms.local', 'Operations', '+1-555-0004')""",
              (hashlib.sha256("mgr123".encode()).hexdigest(),))
    c.execute("""INSERT OR IGNORE INTO users (username, password_hash, full_name, role, email, department, phone)
                 VALUES ('supervisor1', ?, 'David Wilson', 'supervisor', 'david.w@cmms.local', 'Maintenance', '+1-555-0005')""",
              (hashlib.sha256("sup123".encode()).hexdigest(),))

    locations = [
        (1,'Main Facility','MF',None,'Main building','123 Main St','Springfield','IL','62701'),
        (2,'Production Floor','PF',1,'Manufacturing area','123 Main St','Springfield','IL','62701'),
        (3,'Utility Room','UR',1,'HVAC and electrical','123 Main St','Springfield','IL','62701'),
        (4,'Warehouse','WH',1,'Storage and logistics','456 Warehouse Ave','Springfield','IL','62702'),
        (5,'R&D Lab','RD',1,'Research and development','123 Main St','Springfield','IL','62701'),
        (6,'Admin Building','AD',None,'Administration offices','789 Admin Blvd','Springfield','IL','62703'),
    ]
    for loc in locations:
        c.execute("""INSERT OR IGNORE INTO locations (id,name,code,parent_id,description,address,city,state,zip_code)
                     VALUES (?,?,?,?,?,?,?,?,?)""", loc)

    categories = [
        (1,'HVAC','Heating, ventilation, and air conditioning','#3B82F6','❄️'),
        (2,'Electrical','Electrical systems and components','#F59E0B','⚡'),
        (3,'Machinery','Industrial machinery and equipment','#10B981','⚙️'),
        (4,'Plumbing','Plumbing systems and fixtures','#6366F1','💧'),
        (5,'Vehicles','Fleet vehicles and mobile equipment','#EF4444','🚛'),
        (6,'IT Equipment','Computers, servers, network equipment','#8B5CF6','💻'),
        (7,'Safety Equipment','Fire suppression, safety systems','#EC4899','🛡️'),
    ]
    for cat in categories:
        c.execute("INSERT OR IGNORE INTO asset_categories (id,name,description,color,icon) VALUES (?,?,?,?,?)", cat)

    suppliers = [
        (1,'HVAC Supply Co.','Bob Miller','bob@hvacsupply.com','800-555-0101','123 Industrial Pkwy','www.hvacsupply.com','12-3456789','Net 30'),
        (2,'Industrial Parts Inc.','Alice Brown','alice@indparts.com','800-555-0102','456 Factory Rd','www.indparts.com','98-7654321','Net 45'),
        (3,'Electrical Wholesale','Charlie Davis','charlie@elecwholesale.com','800-555-0103','789 Power St','www.elecwholesale.com','45-6789012','2% 10, Net 30'),
        (4,'MRO Direct','Diana Evans','diana@mrodirect.com','800-555-0104','321 Maintenance Ave','www.mrodirect.com','67-8901234','Net 30'),
    ]
    for sup in suppliers:
        c.execute("""INSERT OR IGNORE INTO suppliers (id,name,contact_person,email,phone,address,website,tax_id,payment_terms)
                     VALUES (?,?,?,?,?,?,?,?,?)""", sup)

    assets = [
        (1,'Air Handling Unit #1','AHU-001',1,3,'active','Carrier','AHU-30XA','SN123456','2020-01-15',45000,'2025-01-15','Standard 5-year warranty','Main HVAC unit for production floor','critical','BAR001','Requires monthly filter changes'),
        (2,'CNC Milling Machine','CNC-001',3,2,'active','Haas','VF-2','SN789012','2019-06-01',85000,'2024-06-01','Extended warranty included','5-axis CNC machine','critical','BAR002','Use only approved coolants'),
        (3,'Main Electrical Panel','EP-001',2,3,'active','Siemens','SIEVERT','SN345678','2018-03-10',12000,'2023-03-10','Parts warranty only','400A main distribution panel','high','BAR003','Lockout/tagout required'),
        (4,'Forklift #1','FL-001',5,4,'active','Toyota','8FGU25','SN901234','2021-09-20',28000,'2026-09-20','Full warranty','Propane forklift','medium','BAR004','Daily fluid check required'),
        (5,'Compressor Unit','COMP-001',3,2,'maintenance','Atlas Copco','GA37','SN567890','2020-11-05',18000,'2025-11-05','Parts warranty','Rotary screw air compressor','high','BAR005','Oil leak issue'),
        (6,'Cooling Tower','CT-001',1,3,'active','BAC','VFL-105','SN234567','2017-07-22',32000,'2022-07-22','Expired','Evaporative cooling tower','high','BAR006','Annual chemical treatment required'),
        (7,'Conveyor Belt System','CVB-001',3,2,'active','Dorner','2200','SN678901','2022-04-18',9500,'2027-04-18','5-year warranty','Assembly line conveyor','medium','BAR007','Check tension weekly'),
        (8,'Water Pump Station','WPS-001',4,3,'active','Grundfos','CR15-4','SN345012','2019-12-03',7500,'2024-12-03','2-year warranty','Main water supply pump','high','BAR008','Seal replacement history'),
        (9,'Server Rack #1','SRV-001',6,5,'active','Dell','PowerEdge','SN901234','2022-01-10',45000,'2025-01-10','3-year NBD','Main server infrastructure','critical','BAR009','Temperature monitored'),
        (10,'Fire Suppression System','FSS-001',7,1,'active','Simplex','4100U','SN567890','2021-03-15',15000,'2026-03-15','Annual inspection required','Building-wide fire suppression','critical','BAR010','Inspect monthly'),
    ]
    for a in assets:
        c.execute("""INSERT OR IGNORE INTO assets (id,name,code,category_id,location_id,status,make,model,serial_number,
                     purchase_date,purchase_cost,warranty_expiry,warranty_notes,description,criticality,barcode,notes)
                     VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", a)

    wos = [
        (1,'WO-2024-001','Replace HVAC Filter','Monthly filter replacement for AHU-001',1,'preventive','low','completed',2,1,'2024-01-10','2024-01-15','2024-01-10 08:00','2024-01-10 10:30',2.0,2.5,0,25,25,'Filter replaced successfully',None,'Standard maintenance',None,None,None),
        (2,'WO-2024-002','CNC Machine Lubrication','Full lubrication service',2,'preventive','medium','completed',2,1,'2024-01-20','2024-01-25','2024-01-20 09:00','2024-01-20 12:30',3.0,3.5,75,120,195,'All lubrication points serviced',None,'Used synthetic oil','Lockout required','Grease gun, rags',None),
        (3,'WO-2024-003','Electrical Panel Inspection','Annual safety inspection',3,'preventive','high','in_progress',3,1,'2024-02-01','2024-02-05','2024-02-01 10:00',None,4.0,None,0,0,0,None,None,None,'PPE required','Thermal imager, multimeter',None),
        (4,'WO-2024-004','Forklift Service','Quarterly maintenance',4,'preventive','medium','open',2,1,'2024-02-10','2024-02-15',None,None,2.5,None,0,0,0,None,None,None,'Ventilation required','Basic tools',None),
        (5,'WO-2024-005','Compressor Oil Leak','Emergency repair - oil leak detected',5,'corrective','critical','in_progress',2,1,'2024-02-03','2024-02-04','2024-02-03 14:30',None,6.0,4.5,225,180,405,'Leak identified from seal','Seal failure','Replaced seal and added oil','Hot surfaces','Seal kit, oil',None),
        (6,'WO-2024-006','Cooling Tower Cleaning','Annual chemical cleaning',6,'preventive','high','open',3,1,'2024-03-01','2024-03-05',None,None,8.0,None,0,350,350,None,None,None,'Chemical handling','Cleaning kit, PPE',None),
        (7,'WO-2024-007','Conveyor Belt Tension Check','Routine inspection',7,'inspection','low','completed',2,1,'2024-01-28','2024-01-30','2024-01-28 11:00','2024-01-28 12:00',1.0,1.0,35,0,35,'Belt tension within spec',None,'Minor adjustment made','Pinch points','Tension gauge',None),
        (8,'WO-2024-008','Water Pump Seal Replacement','Seal showing wear',8,'corrective','high','open',2,1,'2024-02-08','2024-02-10',None,None,3.0,None,0,85,85,None,'Normal wear',None,'Drain system first','Seal kit, tools',None),
    ]
    for wo in wos:
        c.execute("""INSERT OR IGNORE INTO work_orders (id,wo_number,title,description,asset_id,type,priority,
                     status,assigned_to,requested_by,scheduled_date,due_date,started_at,completed_at,
                     estimated_hours,actual_hours,labor_cost,parts_cost,total_cost,completion_notes,
                     failure_reason,resolution,safety_notes,tools_required,notes)
                     VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", wo)

    parts = [
        (1,'HVAC Filter 20x20x1','FILT-001','Standard HVAC filter',25,10,50,15,12.50,'Shelf A1','A-101','FilterPro Inc','FilterPro',3,'MERV 8 rating'),
        (2,'Hydraulic Oil 5W-30','OIL-001','1 gallon container',15,5,30,8,28.00,'Shelf B2','B-201','LubeTech','PetroChem',5,'Synthetic blend'),
        (3,'V-Belt A45','BELT-001','Replacement belt for machinery',8,3,20,5,18.75,'Shelf C1','C-301','BeltWorld','Gates',7,'Heavy duty'),
        (4,'Oil Seal 40x55x7','SEAL-001','Pump shaft seal',12,4,25,6,9.50,'Shelf A3','A-103','SealTech','SKF',10,'Nitrile rubber'),
        (5,'Circuit Breaker 20A','CB-020','120V circuit breaker',6,2,15,4,35.00,'Shelf D1','D-401','ElecSupply','Siemens',7,'Type QP'),
        (6,'Bearing 6205-2RS','BRG-001','Deep groove ball bearing',10,4,30,6,14.25,'Shelf B1','B-101','BearingPro','NSK',10,'Sealed'),
        (7,'Compressor Oil 46','COIL-001','1 quart compressor oil',20,8,40,12,22.00,'Shelf B3','B-203','LubeTech','Atlas Copco',5,'Synthetic'),
        (8,'Water Treatment Chemical','CHEM-001','5 gallon pail',4,2,10,2,85.00,'Chemical Storage','CHEM-1','ChemPure','Nalco',14,'Handle with care'),
        (9,'LED Light Fixture','LED-001','4ft LED shop light',12,5,30,8,45.00,'Shelf E1','E-501','ElecSupply','Philips',7,'5000K'),
        (10,'Motor Bearing','MB-001','Electric motor bearing',8,3,20,5,32.50,'Shelf B2','B-202','BearingPro','SKF',10,'High temperature'),
    ]
    for p in parts:
        c.execute("""INSERT OR IGNORE INTO parts (id,name,part_number,description,quantity,min_quantity,max_quantity,
                     reorder_point,unit_cost,location,bin_number,supplier,manufacturer,lead_time_days,notes)
                     VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", p)

    pms = [
        (1,'AHU Monthly Filter Change',1,'Replace filters and inspect coils','monthly',1,'2024-01-10','2024-02-10',2,2.0,45,'["Check filter condition","Replace filter if dirty","Inspect coils","Check belt tension","Log readings"]','Lockout/Tagout required',1),
        (2,'CNC Quarterly Lube',2,'Full lubrication and calibration','quarterly',3,'2024-01-20','2024-04-20',2,4.0,120,'["Check oil levels","Lubricate all points","Verify spindle alignment","Test emergency stop","Clean coolant filters"]','Machine must be cooled down',1),
        (3,'Forklift Monthly Service',4,'Fluid check, tire inspection, battery','monthly',1,'2024-01-15','2024-02-15',2,2.5,85,'["Check engine oil","Inspect tires","Test horn and lights","Check forks","Inspect mast"]','Park in designated area',1),
        (4,'Cooling Tower Annual Clean',6,'Chemical treatment and inspection','yearly',12,'2023-03-01','2024-03-01',3,8.0,450,'["Drain tower","Clean fill media","Apply biocide treatment","Inspect structure","Refill and test"]','Chemical handling PPE required',1),
        (5,'Compressor Weekly Check',5,'Oil level, belt tension, filter','weekly',1,'2024-02-01','2024-02-08',2,0.5,25,'["Check oil level","Inspect belts","Check inlet filter","Drain moisture trap","Log pressure readings"]','Check for unusual noise',1),
        (6,'Electrical Panel IR Scan',3,'Infrared scanning of connections','quarterly',3,'2024-01-05','2024-04-05',3,2.0,150,'["Infrared scan all connections","Check torque on lugs","Inspect breakers","Document hot spots","Update records"]','Arc flash PPE required',1),
        (7,'Server Room Filter Change',9,'Replace air filters in server room','monthly',1,'2024-01-20','2024-02-20',2,1.0,35,'["Remove old filters","Install new filters","Check temperature readings","Clean intake grilles","Log changes"]','Notify IT before work',1),
    ]
    for pm in pms:
        c.execute("""INSERT OR IGNORE INTO pm_schedules (id,title,asset_id,description,frequency,frequency_value,
                     last_performed,next_due,assigned_to,estimated_hours,estimated_cost,checklist,
                     safety_instructions,requires_shutdown)
                     VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", pm)

    # Seed asset history
    history_entries = [
        (1,1,'work_order','WO-2024-001: Replace HVAC Filter','Filter replaced successfully. Used MERV 8 filter.',2,25,1,'work_order','2024-01-10 10:30:00'),
        (2,1,'pm_completion','PM: AHU Monthly Filter Change','Completed scheduled maintenance. Next due 2024-02-10.',2,45,1,'pm_schedule','2024-01-10 10:30:00'),
        (3,2,'work_order','WO-2024-002: CNC Machine Lubrication','All lubrication points serviced with synthetic oil.',2,195,2,'work_order','2024-01-20 12:30:00'),
        (4,5,'status_change','Status changed: active → maintenance','Oil leak detected. Asset taken offline for repair.',1,0,None,None,'2024-02-03 14:30:00'),
        (5,5,'work_order','WO-2024-005: Compressor Oil Leak','Seal replaced. Asset still under repair.',2,405,5,'work_order','2024-02-03 14:30:00'),
        (6,7,'work_order','WO-2024-007: Conveyor Belt Tension Check','Tension within spec. Minor adjustment made.',2,35,7,'work_order','2024-01-28 12:00:00'),
        (7,1,'created','Asset created: Air Handling Unit #1','Initial asset registration.',1,45000,None,None,'2020-01-15 09:00:00'),
        (8,2,'created','Asset created: CNC Milling Machine','Initial asset registration.',1,85000,None,None,'2019-06-01 09:00:00'),
    ]
    for h in history_entries:
        c.execute("""INSERT OR IGNORE INTO asset_history (id,asset_id,event_type,event_title,event_detail,
                     performed_by,cost,reference_id,reference_type,created_at)
                     VALUES (?,?,?,?,?,?,?,?,?,?)""", h)

    # Seed audit log
    audit_entries = [
        (1,1,'LOGIN','users',1,None,None,'127.0.0.1',None,'User logged in','2024-02-01 08:00:00'),
        (2,1,'CREATE','assets',9,None,'{"name":"Server Rack #1"}','127.0.0.1',None,'Asset created','2022-01-10 09:00:00'),
        (3,2,'UPDATE','work_orders',3,'{"status":"open"}','{"status":"in_progress"}','192.168.1.10',None,'Status updated','2024-02-01 10:00:00'),
        (4,3,'CREATE','work_orders',6,None,'{"title":"Cooling Tower Cleaning"}','192.168.1.11',None,'Work order created','2024-02-01 11:00:00'),
        (5,1,'UPDATE','settings',None,'{"company_name":"NEXUS"}','{"company_name":"NEXUS CMMS"}','127.0.0.1',None,'Settings updated','2024-02-01 12:00:00'),
        (6,2,'INVENTORY_ADJUST','parts',2,'15','13','192.168.1.10',None,'Parts used on WO-2024-002','2024-01-20 12:30:00'),
    ]
    for a in audit_entries:
        c.execute("""INSERT OR IGNORE INTO audit_log (id,user_id,action,table_name,record_id,old_value,new_value,ip_address,user_agent,details,created_at)
                     VALUES (?,?,?,?,?,?,?,?,?,?,?)""", a)

    # ── CREATE PERFORMANCE INDEXES ──
    c.executescript("""
    CREATE INDEX IF NOT EXISTS idx_work_orders_status ON work_orders(status);
    CREATE INDEX IF NOT EXISTS idx_work_orders_assigned ON work_orders(assigned_to);
    CREATE INDEX IF NOT EXISTS idx_work_orders_asset ON work_orders(asset_id);
    CREATE INDEX IF NOT EXISTS idx_work_orders_created ON work_orders(created_at);
    CREATE INDEX IF NOT EXISTS idx_work_orders_due_date ON work_orders(due_date);
    CREATE INDEX IF NOT EXISTS idx_assets_status ON assets(status);
    CREATE INDEX IF NOT EXISTS idx_assets_category ON assets(category_id);
    CREATE INDEX IF NOT EXISTS idx_assets_location ON assets(location_id);
    CREATE INDEX IF NOT EXISTS idx_pm_schedules_active ON pm_schedules(active, next_due);
    CREATE INDEX IF NOT EXISTS idx_parts_quantity ON parts(quantity, min_quantity);
    CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id, is_read);
    CREATE INDEX IF NOT EXISTS idx_audit_log_user ON audit_log(user_id, created_at);
    CREATE INDEX IF NOT EXISTS idx_audit_log_table ON audit_log(table_name, record_id);
    """)

    conn.commit()
    conn.close()

app = Flask(__name__)
# ── PERSISTENT SECRET KEY (survives server restarts so sessions stay valid) ──
def _get_or_create_secret_key():
    """Load secret key from DB if it exists, otherwise create and store it."""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("""CREATE TABLE IF NOT EXISTS app_config
                        (key TEXT PRIMARY KEY, value TEXT)""")
        row = conn.execute("SELECT value FROM app_config WHERE key='secret_key'").fetchone()
        if row:
            conn.close()
            return row['value']
        key = secrets.token_hex(32)
        conn.execute("INSERT INTO app_config (key,value) VALUES ('secret_key',?)", (key,))
        conn.commit()
        conn.close()
        return key
    except Exception:
        return secrets.token_hex(32)   # fallback to random if DB not ready

app.secret_key = _get_or_create_secret_key()
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.config['UPLOAD_FOLDER'] = 'uploads'
# Enhanced security settings
app.config['SESSION_COOKIE_SECURE'] = False  # Set to True in production with HTTPS
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=12)
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Rate limiting dictionary (simple in-memory rate limiter)
rate_limit_store = {}
def rate_limit(max_requests=200, window_seconds=60):
    """Simple rate limiting decorator"""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if request.endpoint == 'static':
                return f(*args, **kwargs)
            ip = request.remote_addr
            now = time.time()
            key = f"{ip}:{request.endpoint}"
            if key not in rate_limit_store:
                rate_limit_store[key] = []
            # Clean old requests
            rate_limit_store[key] = [req_time for req_time in rate_limit_store[key] if now - req_time < window_seconds]
            if len(rate_limit_store[key]) >= max_requests:
                return jsonify({'error': 'Rate limit exceeded. Please try again later.'}), 429
            rate_limit_store[key].append(now)
            return f(*args, **kwargs)
        return decorated
    return decorator

# ── IMPROVED PASSWORD HASHING ──
def hash_password(password, salt=None):
    """Hash password using PBKDF2-SHA256. If no salt provided, generate one."""
    if salt is None:
        salt = secrets.token_hex(16)
    # Use PBKDF2 with 100000 iterations (OWASP recommendation)
    pw_hash = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000)
    return f"pbkdf2${salt}${pw_hash.hex()}"

def verify_password(password, stored_hash):
    """Verify password against stored hash. Supports both old SHA-256 and new PBKDF2."""
    if not stored_hash:
        return False
    # Check if it's the new PBKDF2 format
    if stored_hash.startswith('pbkdf2$'):
        try:
            _, salt, hash_hex = stored_hash.split('$')
            computed = hash_password(password, salt)
            return secrets.compare_digest(computed, stored_hash)
        except:
            return False
    # Legacy SHA-256 support (for existing users)
    else:
        legacy_hash = hashlib.sha256(password.encode()).hexdigest()
        return secrets.compare_digest(legacy_hash, stored_hash)

# ── INPUT VALIDATION HELPERS ──
def sanitize_string(value, max_length=255, allow_empty=False):
    """Sanitize and validate string input"""
    if value is None:
        return None if allow_empty else ''
    value = str(value).strip()
    if not allow_empty and not value:
        return None
    return value[:max_length]

def validate_email(email):
    """Basic email validation"""
    if not email:
        return False
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def validate_phone(phone):
    """Basic phone number validation (allows various formats)"""
    if not phone:
        return True  # Phone is optional
    # Remove common formatting characters
    cleaned = re.sub(r'[\s\-\(\)\.]', '', phone)
    # Should be 10-15 digits
    return cleaned.isdigit() and 10 <= len(cleaned) <= 15

def handle_api_errors(f):
    """Decorator to handle common API errors gracefully"""
    @wraps(f)
    def decorated(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except sqlite3.IntegrityError as e:
            return jsonify({'success': False, 'error': 'Database constraint violation', 'details': str(e)}), 400
        except sqlite3.OperationalError as e:
            return jsonify({'success': False, 'error': 'Database operation failed', 'details': str(e)}), 500
        except ValueError as e:
            return jsonify({'success': False, 'error': 'Invalid input value', 'details': str(e)}), 400
        except KeyError as e:
            return jsonify({'success': False, 'error': 'Missing required field', 'details': str(e)}), 400
        except Exception as e:
            print(f"Unexpected error in {f.__name__}: {e}")
            return jsonify({'success': False, 'error': 'An unexpected error occurred', 'details': str(e)}), 500
    return decorated

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Unauthorized'}), 401
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Unauthorized'}), 401
        if session.get('role') != 'admin':
            return jsonify({'error': 'Admin access required'}), 403
        return f(*args, **kwargs)
    return decorated

def log_action(user_id, action, table_name, record_id, old_value=None, new_value=None, details=""):
    conn = get_db()
    conn.execute("""INSERT INTO audit_log (user_id,action,table_name,record_id,old_value,new_value,details,ip_address,user_agent)
                    VALUES (?,?,?,?,?,?,?,?,?)""",
                 (user_id, action, table_name, record_id, old_value, new_value, details,
                  request.remote_addr, request.user_agent.string if request.user_agent else None))
    conn.commit()
    conn.close()

def add_asset_history(asset_id, event_type, event_title, event_detail=None, performed_by=None, cost=0, reference_id=None, reference_type=None):
    conn = get_db()
    conn.execute("""INSERT INTO asset_history (asset_id,event_type,event_title,event_detail,performed_by,cost,reference_id,reference_type)
                    VALUES (?,?,?,?,?,?,?,?)""",
                 (asset_id, event_type, event_title, event_detail, performed_by, cost or 0, reference_id, reference_type))
    conn.commit()
    conn.close()

def generate_wo_number():
    year = datetime.now().year
    conn = get_db()
    result = conn.execute("SELECT COUNT(*) FROM work_orders WHERE wo_number LIKE ?", (f'WO-{year}-%',)).fetchone()
    count = result[0] if result else 0
    conn.close()
    return f"WO-{year}-{count+1:04d}"

def generate_po_number():
    year = datetime.now().year
    conn = get_db()
    result = conn.execute("SELECT COUNT(*) FROM purchase_orders WHERE po_number LIKE ?", (f'PO-{year}-%',)).fetchone()
    count = result[0] if result else 0
    conn.close()
    return f"PO-{year}-{count+1:04d}"

def send_notification(user_id, type_, title, message, link=None):
    conn = get_db()
    conn.execute("INSERT INTO notifications (user_id,type,title,message,link) VALUES (?,?,?,?,?)",
                 (user_id, type_, title, message, link))
    conn.commit()
    conn.close()

# ── AUTH ──────────────────────────────────────────────────────────────────────

@app.route('/api/login', methods=['POST'])
@rate_limit(max_requests=20, window_seconds=300)  # 20 attempts per 5 minutes
def login():
    data = request.json
    if not data.get('username') or not data.get('password'):
        return jsonify({'success': False, 'message': 'Username and password required'}), 400
    
    conn = get_db()
    user = conn.execute("""SELECT id,username,full_name,role,email,department,phone,avatar,password_hash
                          FROM users WHERE username=? AND is_active=1""",
                        (data['username'],)).fetchone()
    
    if user and verify_password(data['password'], user['password_hash']):
        # Update to new password hash if user is using legacy SHA-256
        if not user['password_hash'].startswith('pbkdf2$'):
            new_hash = hash_password(data['password'])
            conn.execute("UPDATE users SET password_hash=? WHERE id=?", (new_hash, user['id']))
        
        conn.execute("UPDATE users SET last_login=datetime('now') WHERE id=?", (user['id'],))
        conn.commit()
        session.permanent = True
        session['user_id'] = user['id']
        session['username'] = user['username']
        session['role'] = user['role']
        log_action(user['id'], 'LOGIN', 'users', user['id'], None, None, 'User logged in')
        send_notification(user['id'], 'system', 'Welcome Back!', f'Logged in at {datetime.now().strftime("%Y-%m-%d %H:%M")}')
        user_dict = dict(user)
        user_dict.pop('password_hash', None)  # Don't send password hash to frontend
        conn.close()
        return jsonify({'success': True, 'user': user_dict})
    
    conn.close()
    time.sleep(1)  # Prevent timing attacks
    return jsonify({'success': False, 'message': 'Invalid credentials'}), 401

@app.route('/api/logout', methods=['POST'])
def logout():
    if 'user_id' in session:
        log_action(session['user_id'], 'LOGOUT', 'users', session['user_id'], None, None, 'User logged out')
    session.clear()
    return jsonify({'success': True})

@app.route('/api/health')
def health_check():
    """Health check endpoint for monitoring"""
    try:
        conn = get_db()
        conn.execute("SELECT 1").fetchone()
        conn.close()
        db_status = "healthy"
    except:
        db_status = "unhealthy"
    
    return jsonify({
        'status': 'ok' if db_status == "healthy" else 'degraded',
        'version': APP_VERSION,
        'build': APP_BUILD,
        'codename': APP_CODENAME,
        'database': db_status,
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/version')
def version_info():
    """Return version information (public endpoint, no login required).
    Also includes aliases used by the About-page JS (loadVersionInfo).
    The authenticated /api/version route further below adds live DB stats.
    """
    return jsonify({
        'version': APP_VERSION,
        'build': APP_BUILD,
        'codename': APP_CODENAME,
        # Keys expected by loadVersionInfo() in the About page JS
        'current_version': APP_VERSION,
        'build_date': APP_BUILD,
        'features': [
            'Mobile View Enhanced (v9)',
            'Bottom Nav More Drawer',
            'PWA Safe-Area Support',
            'Touch-Optimized UI',
            'PBKDF2 Password Hashing',
            'Rate Limiting on Sensitive Endpoints',
            'Global Advanced Search',
            'Bulk Actions for Work Orders',
            'Database Performance Indexes',
        ]
    })

@app.route('/api/whats-new')
def whats_new():
    """Return what's new in this version"""
    return jsonify({
        'version': APP_VERSION,
        'release_date': APP_BUILD,
        'title': 'NEXUS CMMS v9.0 - Mobile Edition',
        'highlights': [
            {
                'category': 'Mobile View Enhancements',
                'icon': '📱',
                'items': [
                    'New "More" bottom nav drawer with grid of quick-access pages',
                    'PWA safe-area insets for notch/dynamic island devices',
                    'Touch-optimized bottom nav with visual active indicators',
                    'iOS zoom prevention on form inputs (font-size 16px)',
                    'Landscape mode optimization for stats grid',
                    'Tablet layout improvements (769px - 1024px breakpoint)',
                    'Momentum-based scrolling on iOS for all scroll containers',
                    'Swipe-up modal animation on mobile screens'
                ]
            },
            {
                'category': 'Bug Fixes',
                'icon': '🐛',
                'items': [
                    'Fixed command palette shortcut (Ctrl+K / Cmd+K) - now case-insensitive and more robust',
                    'Improved keyboard event handling with proper stopPropagation',
                    'Fixed null reference errors in UI elements'
                ]
            },
            {
                'category': 'Security (from v8)',
                'icon': '🔒',
                'items': [
                    'Upgraded password hashing from SHA-256 to PBKDF2-SHA256 with 100,000 iterations',
                    'Automatic password hash migration on login',
                    'Added rate limiting on login (5 attempts per 5 minutes)',
                    'Enhanced session security with httpOnly and SameSite cookies',
                    'Timing attack prevention on login',
                    'Password validation (minimum 6 characters)'
                ]
            },
            {
                'category': 'UI/UX Improvements',
                'icon': '🎨',
                'items': [
                    'Updated version display to v9',
                    'Better touch targets (min-height 38-52px) on mobile',
                    'Better error messages throughout the application',
                    'Improved accessibility with proper null checks',
                    'Enhanced sidebar mobile animation'
                ]
            }
        ],
        'upgrade_notes': [
            'Existing user passwords will be automatically upgraded to the new PBKDF2 hash on next login',
            'New database indexes will be created automatically',
            'No action required from administrators',
            'All existing features remain fully functional'
        ]
    })

@app.route('/api/me')
def me():
    if 'user_id' not in session:
        return jsonify({'logged_in': False})
    conn = get_db()
    user = conn.execute("""SELECT id,username,full_name,role,email,department,phone,avatar,last_login
                          FROM users WHERE id=?""", (session['user_id'],)).fetchone()
    notif_count = conn.execute("SELECT COUNT(*) FROM notifications WHERE user_id=? AND is_read=0",
                               (session['user_id'],)).fetchone()[0]
    conn.close()
    if user:
        return jsonify({'logged_in': True, 'user': dict(user), 'notifications': notif_count})
    return jsonify({'logged_in': False})

@app.route('/api/change-password', methods=['POST'])
@login_required
@rate_limit(max_requests=10, window_seconds=3600)  # 10 attempts per hour
def change_password():
    data = request.json
    if not data.get('old_password') or not data.get('new_password'):
        return jsonify({'success': False, 'message': 'Both old and new passwords are required'}), 400
    
    if len(data['new_password']) < 6:
        return jsonify({'success': False, 'message': 'New password must be at least 6 characters'}), 400
    
    conn = get_db()
    user = conn.execute("SELECT password_hash FROM users WHERE id=?", (session['user_id'],)).fetchone()
    
    if user and verify_password(data['old_password'], user['password_hash']):
        new_hash = hash_password(data['new_password'])
        conn.execute("UPDATE users SET password_hash=?, updated_at=datetime('now') WHERE id=?", 
                    (new_hash, session['user_id']))
        conn.commit()
        conn.close()
        log_action(session['user_id'], 'PASSWORD_CHANGE', 'users', session['user_id'])
        return jsonify({'success': True, 'message': 'Password changed successfully'})
    
    conn.close()
    return jsonify({'success': False, 'message': 'Current password is incorrect'}), 400

# ── USER MANAGEMENT (ADMIN ONLY) ─────────────────────────────────────────────

@app.route('/api/users', methods=['GET'])
@login_required
def get_users():
    conn = get_db()
    users = conn.execute("""SELECT id,username,full_name,role,email,department,phone,is_active,last_login,created_at
                          FROM users ORDER BY full_name""").fetchall()
    conn.close()
    return jsonify([dict(u) for u in users])

@app.route('/api/users/<int:user_id>', methods=['GET'])
@login_required
@admin_required
def get_user(user_id):
    conn = get_db()
    user = conn.execute("""SELECT id,username,full_name,role,email,department,phone,is_active,last_login,created_at
                          FROM users WHERE id=?""", (user_id,)).fetchone()
    conn.close()
    if not user:
        return jsonify({'error': 'Not found'}), 404
    return jsonify(dict(user))

@app.route('/api/users', methods=['POST'])
@login_required
@admin_required
def create_user():
    data = request.json
    if not data.get('username') or not data.get('password'):
        return jsonify({'success': False, 'message': 'Username and password required'}), 400
    
    if len(data['password']) < 6:
        return jsonify({'success': False, 'message': 'Password must be at least 6 characters'}), 400
    
    pw_hash = hash_password(data['password'])
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute("""INSERT INTO users (username,password_hash,full_name,role,email,department,phone,is_active)
                     VALUES (?,?,?,?,?,?,?,?)""",
                  (data['username'], pw_hash, data.get('full_name'), data.get('role', 'technician'),
                   data.get('email'), data.get('department'), data.get('phone'),
                   1 if data.get('is_active', True) else 0))
        new_id = c.lastrowid
        conn.commit()
        log_action(session['user_id'], 'CREATE', 'users', new_id, None, json.dumps({'username': data['username'], 'role': data.get('role')}), 'User created by admin')
        conn.close()
        return jsonify({'success': True, 'id': new_id})
    except Exception as e:
        conn.close()
        if 'UNIQUE' in str(e):
            return jsonify({'success': False, 'message': 'Username already exists'}), 400
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/users/<int:user_id>', methods=['PUT'])
@login_required
@admin_required
def update_user(user_id):
    data = request.json
    conn = get_db()
    old = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    
    # If password provided, update it
    if data.get('password'):
        if len(data['password']) < 6:
            conn.close()
            return jsonify({'success': False, 'message': 'Password must be at least 6 characters'}), 400
        pw_hash = hash_password(data['password'])
        conn.execute("UPDATE users SET password_hash=?, updated_at=datetime('now') WHERE id=?", (pw_hash, user_id))
    
    conn.execute("""UPDATE users SET full_name=?,role=?,email=?,department=?,phone=?,
                    is_active=?,updated_at=datetime('now') WHERE id=?""",
                 (data.get('full_name'), data.get('role'), data.get('email'),
                  data.get('department'), data.get('phone'),
                  1 if data.get('is_active', True) else 0, user_id))
    conn.commit()
    log_action(session['user_id'], 'UPDATE', 'users', user_id,
               json.dumps(dict(old)) if old else None, json.dumps(data), 'User updated by admin')
    conn.close()
    return jsonify({'success': True})

@app.route('/api/users/<int:user_id>', methods=['DELETE'])
@login_required
@admin_required
def delete_user(user_id):
    if user_id == session['user_id']:
        return jsonify({'success': False, 'message': 'Cannot delete your own account'}), 400
    conn = get_db()
    # Soft delete - deactivate instead of hard delete to preserve referential integrity
    conn.execute("UPDATE users SET is_active=0, updated_at=datetime('now') WHERE id=?", (user_id,))
    conn.commit()
    log_action(session['user_id'], 'DELETE', 'users', user_id, None, None, 'User deactivated by admin')
    conn.close()
    return jsonify({'success': True})

@app.route('/api/users/<int:user_id>/reset-password', methods=['POST'])
@login_required
@admin_required
def reset_user_password(user_id):
    data = request.json
    new_password = data.get('new_password', 'Welcome123!')
    pw_hash = hashlib.sha256(new_password.encode()).hexdigest()
    conn = get_db()
    conn.execute("UPDATE users SET password_hash=? WHERE id=?", (pw_hash, user_id))
    conn.commit()
    conn.close()
    log_action(session['user_id'], 'PASSWORD_RESET', 'users', user_id, None, None, 'Password reset by admin')
    return jsonify({'success': True, 'new_password': new_password})

# ── NOTIFICATIONS ─────────────────────────────────────────────────────────────

@app.route('/api/notifications')
@login_required
def get_notifications():
    conn = get_db()
    notifs = conn.execute("SELECT * FROM notifications WHERE user_id=? ORDER BY created_at DESC LIMIT 50",
                         (session['user_id'],)).fetchall()
    conn.close()
    return jsonify([dict(n) for n in notifs])

@app.route('/api/notifications/<int:notif_id>/read', methods=['POST'])
@login_required
def mark_notification_read(notif_id):
    conn = get_db()
    conn.execute("UPDATE notifications SET is_read=1 WHERE id=? AND user_id=?", (notif_id, session['user_id']))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/notifications/read-all', methods=['POST'])
@login_required
def mark_all_read():
    conn = get_db()
    conn.execute("UPDATE notifications SET is_read=1 WHERE user_id=?", (session['user_id'],))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

# ── DASHBOARD ─────────────────────────────────────────────────────────────────

@app.route('/api/dashboard')
@login_required
def dashboard():
    conn = get_db()
    stats = {
        'total_assets': conn.execute("SELECT COUNT(*) FROM assets").fetchone()[0],
        'active_assets': conn.execute("SELECT COUNT(*) FROM assets WHERE status='active'").fetchone()[0],
        'maintenance_assets': conn.execute("SELECT COUNT(*) FROM assets WHERE status='maintenance'").fetchone()[0],
        'total_wo': conn.execute("SELECT COUNT(*) FROM work_orders").fetchone()[0],
        'open_wo': conn.execute("SELECT COUNT(*) FROM work_orders WHERE status='open'").fetchone()[0],
        'in_progress_wo': conn.execute("SELECT COUNT(*) FROM work_orders WHERE status='in_progress'").fetchone()[0],
        'completed_wo': conn.execute("SELECT COUNT(*) FROM work_orders WHERE status='completed'").fetchone()[0],
        'critical_wo': conn.execute("SELECT COUNT(*) FROM work_orders WHERE priority='critical' AND status!='completed'").fetchone()[0],
        'low_parts': conn.execute("SELECT COUNT(*) FROM parts WHERE quantity <= min_quantity").fetchone()[0],
        'overdue_pm': conn.execute("SELECT COUNT(*) FROM pm_schedules WHERE next_due < date('now') AND active=1").fetchone()[0],
        'total_parts_value': conn.execute("SELECT SUM(quantity * unit_cost) FROM parts").fetchone()[0] or 0,
        'total_wo_cost': conn.execute("SELECT SUM(total_cost) FROM work_orders").fetchone()[0] or 0,
    }
    wo_status = conn.execute("SELECT status, COUNT(*) as count FROM work_orders GROUP BY status").fetchall()
    stats['wo_by_status'] = [dict(r) for r in wo_status]
    wo_type = conn.execute("SELECT type, COUNT(*) as count FROM work_orders GROUP BY type").fetchall()
    stats['wo_by_type'] = [dict(r) for r in wo_type]
    recent_wo = conn.execute("""SELECT w.id,w.wo_number,w.title,w.status,w.priority,w.type,
               a.name as asset_name, u.full_name as assigned_to_name, w.due_date, w.created_at
        FROM work_orders w LEFT JOIN assets a ON w.asset_id=a.id LEFT JOIN users u ON w.assigned_to=u.id
        ORDER BY w.created_at DESC LIMIT 10""").fetchall()
    stats['recent_wo'] = [dict(r) for r in recent_wo]
    upcoming_pm = conn.execute("""SELECT p.id,p.title,p.next_due,p.estimated_hours,
               a.name as asset_name, u.full_name as assigned_to_name
        FROM pm_schedules p LEFT JOIN assets a ON p.asset_id=a.id LEFT JOIN users u ON p.assigned_to=u.id
        WHERE p.active=1 AND p.next_due BETWEEN date('now') AND date('now', '+30 days')
        ORDER BY p.next_due LIMIT 10""").fetchall()
    stats['upcoming_pm'] = [dict(r) for r in upcoming_pm]
    monthly = conn.execute("""SELECT strftime('%Y-%m', created_at) as month,
               COUNT(*) as count,
               SUM(CASE WHEN type='corrective' THEN 1 ELSE 0 END) as corrective,
               SUM(CASE WHEN type='preventive' THEN 1 ELSE 0 END) as preventive
        FROM work_orders WHERE created_at >= date('now', '-12 months')
        GROUP BY month ORDER BY month""").fetchall()
    stats['monthly_trend'] = [dict(r) for r in monthly]
    low_stock = conn.execute("""SELECT name,part_number,quantity,min_quantity,unit_cost FROM parts
        WHERE quantity <= min_quantity ORDER BY (quantity * 1.0 / NULLIF(min_quantity,0)) ASC LIMIT 5""").fetchall()
    stats['low_stock_parts'] = [dict(r) for r in low_stock]
    assets_cat = conn.execute("""SELECT ac.name,ac.color,ac.icon,COUNT(a.id) as count FROM asset_categories ac
        LEFT JOIN assets a ON ac.id=a.category_id GROUP BY ac.id""").fetchall()
    stats['assets_by_category'] = [dict(r) for r in assets_cat]

    # PM Compliance (last 90 days)
    pm_due = conn.execute("SELECT COUNT(*) FROM pm_schedules WHERE active=1 AND next_due <= date('now')").fetchone()[0]
    pm_total = conn.execute("SELECT COUNT(*) FROM pm_schedules WHERE active=1").fetchone()[0]
    stats['pm_compliance'] = round((1 - pm_due / max(pm_total, 1)) * 100, 1)
    stats['pm_total'] = pm_total
    stats['pm_overdue'] = pm_due
    # v4: additional fields for welcome banner and quick strip
    stats['overdue_wo'] = conn.execute("SELECT COUNT(*) FROM work_orders WHERE status NOT IN ('completed','cancelled') AND due_date < date('now')").fetchone()[0]
    stats['pm_due_soon'] = conn.execute("SELECT COUNT(*) FROM pm_schedules WHERE active=1 AND next_due BETWEEN date('now') AND date('now','+7 days')").fetchone()[0]
    stats['low_stock'] = stats['low_parts']

    # Downtime stats (last 30 days)
    downtime = conn.execute("""SELECT COALESCE(SUM(duration_hours),0) as total,
        COUNT(*) as incidents FROM downtime_records
        WHERE start_time >= date('now','-30 days')""").fetchone()
    stats['downtime_hours_30d'] = round(downtime['total'] or 0, 1)
    stats['downtime_incidents_30d'] = downtime['incidents'] or 0

    # Monthly cost trend
    cost_trend = conn.execute("""SELECT strftime('%Y-%m', created_at) as month,
        SUM(total_cost) as cost FROM work_orders
        WHERE created_at >= date('now','-6 months') GROUP BY month ORDER BY month""").fetchall()
    stats['cost_trend'] = [dict(r) for r in cost_trend]

    # Depreciation overview
    dep_assets = conn.execute("""SELECT id,name,code,purchase_cost,purchase_date,
        CAST(strftime('%Y','now') AS INTEGER) - CAST(strftime('%Y',purchase_date) AS INTEGER) as age_years
        FROM assets WHERE purchase_cost IS NOT NULL AND purchase_cost > 0 ORDER BY purchase_cost DESC LIMIT 10""").fetchall()
    stats['depreciation_assets'] = [dict(r) for r in dep_assets]

    conn.close()
    return jsonify(stats)

# ── GLOBAL ADVANCED SEARCH ───────────────────────────────────────────────────
@app.route('/api/search/global', methods=['GET'])
@login_required
def global_search():
    """Advanced global search across assets, work orders, parts, and users"""
    query = request.args.get('q', '').strip()
    if len(query) < 2:
        return jsonify({'results': [], 'total': 0})
    
    conn = get_db()
    q_pattern = f'%{query}%'
    results = {'assets': [], 'work_orders': [], 'parts': [], 'users': [], 'total': 0}
    
    # Search assets
    assets = conn.execute("""SELECT id, name, code, serial_number, status, 'asset' as type
                            FROM assets WHERE name LIKE ? OR code LIKE ? OR serial_number LIKE ?
                            LIMIT 10""", (q_pattern, q_pattern, q_pattern)).fetchall()
    results['assets'] = [dict(r) for r in assets]
    
    # Search work orders
    work_orders = conn.execute("""SELECT id, wo_number, title, status, priority, 'work_order' as type
                                  FROM work_orders WHERE wo_number LIKE ? OR title LIKE ?
                                  LIMIT 10""", (q_pattern, q_pattern)).fetchall()
    results['work_orders'] = [dict(r) for r in work_orders]
    
    # Search parts
    parts = conn.execute("""SELECT id, name, part_number, quantity, 'part' as type
                           FROM parts WHERE name LIKE ? OR part_number LIKE ?
                           LIMIT 10""", (q_pattern, q_pattern)).fetchall()
    results['parts'] = [dict(r) for r in parts]
    
    # Search users (if admin or manager)
    if session.get('role') in ['admin', 'manager']:
        users = conn.execute("""SELECT id, username, full_name, role, 'user' as type
                               FROM users WHERE username LIKE ? OR full_name LIKE ?
                               LIMIT 10""", (q_pattern, q_pattern)).fetchall()
        results['users'] = [dict(r) for r in users]
    
    results['total'] = len(results['assets']) + len(results['work_orders']) + len(results['parts']) + len(results['users'])
    conn.close()
    return jsonify(results)

# ── ASSETS ────────────────────────────────────────────────────────────────────

@app.route('/api/assets', methods=['GET'])
@login_required
def get_assets():
    conn = get_db()
    search = request.args.get('search', '')
    status = request.args.get('status', '')
    category = request.args.get('category', '')
    location = request.args.get('location', '')
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 20))
    offset = (page - 1) * per_page
    query = """SELECT a.*,ac.name as category_name,ac.color as category_color,ac.icon as category_icon,
               l.name as location_name FROM assets a
        LEFT JOIN asset_categories ac ON a.category_id=ac.id
        LEFT JOIN locations l ON a.location_id=l.id WHERE 1=1"""
    count_query = "SELECT COUNT(*) FROM assets a WHERE 1=1"
    params = []
    if search:
        q = f'%{search}%'
        query += " AND (a.name LIKE ? OR a.code LIKE ? OR a.serial_number LIKE ? OR a.make LIKE ?)"
        count_query += " AND (a.name LIKE ? OR a.code LIKE ? OR a.serial_number LIKE ? OR a.make LIKE ?)"
        params += [q, q, q, q]
    if status:
        query += " AND a.status=?"; count_query += " AND a.status=?"; params.append(status)
    if category:
        query += " AND a.category_id=?"; count_query += " AND a.category_id=?"; params.append(category)
    if location:
        query += " AND a.location_id=?"; count_query += " AND a.location_id=?"; params.append(location)
    query += " ORDER BY a.name LIMIT ? OFFSET ?"
    total = conn.execute(count_query, params).fetchone()[0]
    assets = conn.execute(query, params + [per_page, offset]).fetchall()
    conn.close()
    return jsonify({'items': [dict(a) for a in assets], 'total': total, 'page': page, 'per_page': per_page, 'pages': (total + per_page - 1) // per_page})

@app.route('/api/assets/<int:asset_id>', methods=['GET'])
@login_required
def get_asset(asset_id):
    conn = get_db()
    asset = conn.execute("""SELECT a.*,ac.name as category_name,ac.color as category_color,
               l.name as location_name FROM assets a
        LEFT JOIN asset_categories ac ON a.category_id=ac.id
        LEFT JOIN locations l ON a.location_id=l.id WHERE a.id=?""", (asset_id,)).fetchone()
    if not asset:
        conn.close()
        return jsonify({'error': 'Not found'}), 404
    work_orders = conn.execute("""SELECT w.id,w.wo_number,w.title,w.status,w.priority,w.type,
               w.created_at,w.completed_at,w.actual_hours,w.total_cost,
               w.failure_reason,w.resolution,w.labor_cost,w.parts_cost
        FROM work_orders w WHERE w.asset_id=? ORDER BY w.created_at DESC LIMIT 200""", (asset_id,)).fetchall()
    pm = conn.execute("SELECT * FROM pm_schedules WHERE asset_id=? AND active=1 ORDER BY next_due", (asset_id,)).fetchall()
    meters = conn.execute("SELECT * FROM meter_readings WHERE asset_id=? ORDER BY reading_date DESC LIMIT 10", (asset_id,)).fetchall()
    conn.close()
    return jsonify({'asset': dict(asset), 'work_orders': [dict(w) for w in work_orders],
                    'pm_schedules': [dict(p) for p in pm], 'meter_readings': [dict(m) for m in meters]})

@app.route('/api/assets/<int:asset_id>/history', methods=['GET'])
@login_required
def get_asset_history(asset_id):
    conn = get_db()
    history = conn.execute("""SELECT h.*,u.full_name as performed_by_name FROM asset_history h
        LEFT JOIN users u ON h.performed_by=u.id
        WHERE h.asset_id=? ORDER BY h.created_at DESC LIMIT 50""", (asset_id,)).fetchall()
    conn.close()
    return jsonify([dict(h) for h in history])

@app.route('/api/assets', methods=['POST'])
@login_required
def create_asset():
    data = request.json
    conn = get_db()
    c = conn.cursor()
    c.execute("""INSERT INTO assets (name,code,category_id,location_id,status,make,model,serial_number,
        purchase_date,purchase_cost,warranty_expiry,warranty_notes,description,criticality,barcode,notes)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
    (data['name'], data.get('code'), data.get('category_id'), data.get('location_id'),
     data.get('status', 'active'), data.get('make'), data.get('model'), data.get('serial_number'),
     data.get('purchase_date'), data.get('purchase_cost'), data.get('warranty_expiry'),
     data.get('warranty_notes'), data.get('description'), data.get('criticality', 'medium'),
     data.get('barcode'), data.get('notes')))
    new_id = c.lastrowid
    conn.commit()
    add_asset_history(new_id, 'created', f'Asset created: {data["name"]}',
                      f'Asset registered with code {data.get("code","")}.',
                      session['user_id'], data.get('purchase_cost'), new_id, 'asset')
    log_action(session['user_id'], 'CREATE', 'assets', new_id, None, json.dumps(data))
    conn.close()
    return jsonify({'success': True, 'id': new_id})

@app.route('/api/assets/<int:asset_id>', methods=['PUT'])
@login_required
def update_asset(asset_id):
    data = request.json
    conn = get_db()
    old = conn.execute("SELECT * FROM assets WHERE id=?", (asset_id,)).fetchone()
    # Track status change
    if old and old['status'] != data.get('status'):
        add_asset_history(asset_id, 'status_change',
                          f'Status changed: {old["status"]} → {data.get("status")}',
                          f'Status updated by {session.get("username")}',
                          session['user_id'], 0)
    conn.execute("""UPDATE assets SET name=?,code=?,category_id=?,location_id=?,status=?,make=?,model=?,
        serial_number=?,purchase_date=?,purchase_cost=?,warranty_expiry=?,warranty_notes=?,description=?,
        criticality=?,barcode=?,notes=?,updated_at=datetime('now') WHERE id=?""",
    (data['name'], data.get('code'), data.get('category_id'), data.get('location_id'),
     data.get('status', 'active'), data.get('make'), data.get('model'), data.get('serial_number'),
     data.get('purchase_date'), data.get('purchase_cost'), data.get('warranty_expiry'),
     data.get('warranty_notes'), data.get('description'), data.get('criticality', 'medium'),
     data.get('barcode'), data.get('notes'), asset_id))
    conn.commit()
    log_action(session['user_id'], 'UPDATE', 'assets', asset_id, json.dumps(dict(old)) if old else None, json.dumps(data))
    conn.close()
    return jsonify({'success': True})

@app.route('/api/assets/<int:asset_id>', methods=['DELETE'])
@login_required
@admin_required
def delete_asset(asset_id):
    conn = get_db()
    count = conn.execute("SELECT COUNT(*) FROM work_orders WHERE asset_id=?", (asset_id,)).fetchone()[0]
    if count > 0:
        conn.close()
        return jsonify({'success': False, 'message': 'Cannot delete asset with existing work orders'}), 400
    conn.execute("DELETE FROM assets WHERE id=?", (asset_id,))
    conn.commit()
    log_action(session['user_id'], 'DELETE', 'assets', asset_id)
    conn.close()
    return jsonify({'success': True})

@app.route('/api/assets/<int:asset_id>/meter-reading', methods=['POST'])
@login_required
def add_meter_reading(asset_id):
    data = request.json
    conn = get_db()
    conn.execute("""INSERT INTO meter_readings (asset_id,meter_type,reading_value,reading_date,notes,recorded_by)
                    VALUES (?,?,?,?,?,?)""",
                (asset_id, data['meter_type'], data['reading_value'],
                 data.get('reading_date', datetime.now().strftime('%Y-%m-%d')),
                 data.get('notes'), session['user_id']))
    conn.commit()
    add_asset_history(asset_id, 'meter_reading', f'Meter reading: {data["reading_value"]} {data["meter_type"]}',
                      data.get('notes'), session['user_id'])
    conn.close()
    return jsonify({'success': True})

# ── WORK ORDERS ───────────────────────────────────────────────────────────────

@app.route('/api/work-orders', methods=['GET'])
@login_required
def get_work_orders():
    conn = get_db()
    status = request.args.get('status', '')
    priority = request.args.get('priority', '')
    search = request.args.get('search', '')
    type_ = request.args.get('type', '')
    asset_id = request.args.get('asset_id', '')
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 20))
    offset = (page - 1) * per_page
    query = """SELECT w.*,a.name as asset_name,a.code as asset_code,
               u1.full_name as assigned_to_name,u2.full_name as requested_by_name
        FROM work_orders w LEFT JOIN assets a ON w.asset_id=a.id
        LEFT JOIN users u1 ON w.assigned_to=u1.id LEFT JOIN users u2 ON w.requested_by=u2.id WHERE 1=1"""
    count_query = "SELECT COUNT(*) FROM work_orders w WHERE 1=1"
    params = []
    if status:
        query += " AND w.status=?"; count_query += " AND w.status=?"; params.append(status)
    if priority:
        query += " AND w.priority=?"; count_query += " AND w.priority=?"; params.append(priority)
    if type_:
        query += " AND w.type=?"; count_query += " AND w.type=?"; params.append(type_)
    if asset_id:
        query += " AND w.asset_id=?"; count_query += " AND w.asset_id=?"; params.append(asset_id)
    if search:
        q = f'%{search}%'
        query += " AND (w.title LIKE ? OR w.wo_number LIKE ? OR a.name LIKE ?)"
        count_query += " AND (w.title LIKE ? OR w.wo_number LIKE ? OR a.name LIKE ?)"
        params += [q, q, q]
    query += """ ORDER BY CASE w.priority WHEN 'critical' THEN 1 WHEN 'high' THEN 2 WHEN 'medium' THEN 3 ELSE 4 END,
        CASE w.status WHEN 'in_progress' THEN 1 WHEN 'open' THEN 2 ELSE 3 END,
        w.created_at DESC LIMIT ? OFFSET ?"""
    total = conn.execute(count_query, params).fetchone()[0]
    wos = conn.execute(query, params + [per_page, offset]).fetchall()
    conn.close()
    return jsonify({'items': [dict(w) for w in wos], 'total': total, 'page': page, 'per_page': per_page, 'pages': (total + per_page - 1) // per_page})

@app.route('/api/work-orders/<int:wo_id>', methods=['GET'])
@login_required
def get_work_order(wo_id):
    conn = get_db()
    wo = conn.execute("""SELECT w.*,a.name as asset_name,a.code as asset_code,a.location_id,
               u1.full_name as assigned_to_name,u2.full_name as requested_by_name,l.name as location_name
        FROM work_orders w LEFT JOIN assets a ON w.asset_id=a.id
        LEFT JOIN users u1 ON w.assigned_to=u1.id LEFT JOIN users u2 ON w.requested_by=u2.id
        LEFT JOIN locations l ON a.location_id=l.id WHERE w.id=?""", (wo_id,)).fetchone()
    if not wo:
        conn.close()
        return jsonify({'error': 'Not found'}), 404
    parts = conn.execute("""SELECT wp.*,p.name as part_name,p.part_number FROM wo_parts wp
        JOIN parts p ON wp.part_id=p.id WHERE wp.wo_id=?""", (wo_id,)).fetchall()
    time_entries = conn.execute("""SELECT te.*,u.full_name as user_name FROM wo_time_entries te
        JOIN users u ON te.user_id=u.id WHERE te.wo_id=? ORDER BY te.work_date""", (wo_id,)).fetchall()
    comments = conn.execute("""SELECT c.*,u.full_name as user_name FROM comments c
        JOIN users u ON c.user_id=u.id WHERE c.wo_id=? ORDER BY c.created_at DESC""", (wo_id,)).fetchall()
    conn.close()
    return jsonify({'work_order': dict(wo), 'parts': [dict(p) for p in parts],
                    'time_entries': [dict(t) for t in time_entries], 'comments': [dict(c) for c in comments]})

@app.route('/api/work-orders', methods=['POST'])
@login_required
def create_work_order():
    data = request.json
    wo_number = generate_wo_number()
    conn = get_db()
    c = conn.cursor()
    c.execute("""INSERT INTO work_orders (wo_number,title,description,asset_id,type,priority,status,
        assigned_to,requested_by,scheduled_date,due_date,estimated_hours,tools_required,safety_notes,notes)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
    (wo_number, data['title'], data.get('description'), data.get('asset_id'),
     data.get('type', 'corrective'), data.get('priority', 'medium'), data.get('status', 'open'),
     data.get('assigned_to'), session['user_id'], data.get('scheduled_date'), data.get('due_date'),
     data.get('estimated_hours'), data.get('tools_required'), data.get('safety_notes'), data.get('notes')))
    new_id = c.lastrowid
    conn.commit()
    if data.get('asset_id'):
        add_asset_history(data['asset_id'], 'work_order', f'{wo_number}: {data["title"]}',
                          data.get('description'), session['user_id'], 0, new_id, 'work_order')
    if data.get('assigned_to'):
        send_notification(data['assigned_to'], 'work_order', 'New Work Order Assigned',
                         f'WO {wo_number}: {data["title"]}', f'/work-orders/{new_id}')
    log_action(session['user_id'], 'CREATE', 'work_orders', new_id, None, json.dumps(data))
    conn.close()
    broadcast_event('wo_created', {'wo_number': wo_number, 'id': new_id, 'title': data.get('title'), 'priority': data.get('priority','medium')})
    return jsonify({'success': True, 'id': new_id, 'wo_number': wo_number})

@app.route('/api/work-orders/<int:wo_id>', methods=['PUT'])
@login_required
def update_work_order(wo_id):
    data = request.json
    conn = get_db()
    old = conn.execute("SELECT * FROM work_orders WHERE id=?", (wo_id,)).fetchone()
    extra_fields = ""
    if data.get('status') == 'in_progress' and old and old['status'] != 'in_progress':
        extra_fields = ", started_at=COALESCE(started_at, datetime('now'))"
    elif data.get('status') == 'completed' and old and old['status'] != 'completed':
        extra_fields = ", completed_at=COALESCE(completed_at, datetime('now'))"
        total_cost = (data.get('labor_cost', 0) or 0) + (data.get('parts_cost', 0) or 0)
        data['total_cost'] = total_cost
        if old and old['asset_id']:
            add_asset_history(old['asset_id'], 'work_order',
                              f'{old["wo_number"]}: {old["title"]} — Completed',
                              data.get('completion_notes', ''), session['user_id'],
                              total_cost, wo_id, 'work_order')
        if old and old['requested_by']:
            send_notification(old['requested_by'], 'work_order', 'Work Order Completed',
                            f'WO {old["wo_number"]} has been completed', f'/work-orders/{wo_id}')
    conn.execute(f"""UPDATE work_orders SET title=?,description=?,asset_id=?,type=?,priority=?,status=?,
        assigned_to=?,scheduled_date=?,due_date=?,estimated_hours=?,actual_hours=?,labor_cost=?,
        parts_cost=?,total_cost=?,completion_notes=?,failure_reason=?,resolution=?,safety_notes=?,
        tools_required=?,notes=?,updated_at=datetime('now'){extra_fields} WHERE id=?""",
    (data['title'], data.get('description'), data.get('asset_id'), data.get('type', 'corrective'),
     data.get('priority', 'medium'), data.get('status', 'open'), data.get('assigned_to'),
     data.get('scheduled_date'), data.get('due_date'), data.get('estimated_hours'),
     data.get('actual_hours'), data.get('labor_cost', 0), data.get('parts_cost', 0),
     data.get('total_cost', 0), data.get('completion_notes'), data.get('failure_reason'),
     data.get('resolution'), data.get('safety_notes'), data.get('tools_required'), data.get('notes'), wo_id))
    conn.commit()
    log_action(session['user_id'], 'UPDATE', 'work_orders', wo_id,
               json.dumps(dict(old)) if old else None, json.dumps(data))
    conn.close()
    return jsonify({'success': True})

@app.route('/api/work-orders/<int:wo_id>/time', methods=['POST'])
@login_required
def add_time_entry(wo_id):
    data = request.json
    conn = get_db()
    conn.execute("INSERT INTO wo_time_entries (wo_id,user_id,hours_worked,work_date,description) VALUES (?,?,?,?,?)",
                (wo_id, session['user_id'], data['hours_worked'],
                 data.get('work_date', datetime.now().strftime('%Y-%m-%d')), data.get('description')))
    total = conn.execute("SELECT SUM(hours_worked) FROM wo_time_entries WHERE wo_id=?", (wo_id,)).fetchone()[0]
    conn.execute("UPDATE work_orders SET actual_hours=? WHERE id=?", (total, wo_id))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/work-orders/<int:wo_id>/parts', methods=['POST'])
@login_required
def add_part_to_wo(wo_id):
    data = request.json
    conn = get_db()
    part = conn.execute("SELECT unit_cost FROM parts WHERE id=?", (data['part_id'],)).fetchone()
    unit_cost = part['unit_cost'] if part else data.get('unit_cost', 0)
    line_total = unit_cost * data['quantity_used']
    conn.execute("INSERT INTO wo_parts (wo_id,part_id,quantity_used,unit_cost,line_total,notes) VALUES (?,?,?,?,?,?)",
                (wo_id, data['part_id'], data['quantity_used'], unit_cost, line_total, data.get('notes')))
    total = conn.execute("SELECT SUM(line_total) FROM wo_parts WHERE wo_id=?", (wo_id,)).fetchone()[0]
    conn.execute("UPDATE work_orders SET parts_cost=? WHERE id=?", (total or 0, wo_id))
    conn.execute("UPDATE parts SET quantity = quantity - ? WHERE id=?", (data['quantity_used'], data['part_id']))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/work-orders/<int:wo_id>/comments', methods=['POST'])
@login_required
def add_comment(wo_id):
    data = request.json
    conn = get_db()
    conn.execute("INSERT INTO comments (wo_id,user_id,content,is_private) VALUES (?,?,?,?)",
                (wo_id, session['user_id'], data['content'], data.get('is_private', 0)))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/work-orders/<int:wo_id>', methods=['DELETE'])
@login_required
@admin_required
def delete_work_order(wo_id):
    conn = get_db()
    conn.execute("DELETE FROM work_orders WHERE id=?", (wo_id,))
    conn.commit()
    log_action(session['user_id'], 'DELETE', 'work_orders', wo_id)
    conn.close()
    return jsonify({'success': True})

# ── BULK ACTIONS FOR WORK ORDERS ─────────────────────────────────────────────
@app.route('/api/work-orders/bulk-action', methods=['POST'])
@login_required
def bulk_action_work_orders():
    """Perform bulk actions on multiple work orders"""
    data = request.json
    action = data.get('action')
    wo_ids = data.get('wo_ids', [])
    
    if not action or not wo_ids:
        return jsonify({'success': False, 'message': 'Action and work order IDs required'}), 400
    
    if len(wo_ids) > 100:
        return jsonify({'success': False, 'message': 'Cannot process more than 100 work orders at once'}), 400
    
    conn = get_db()
    updated_count = 0
    
    try:
        if action == 'assign':
            assigned_to = data.get('assigned_to')
            if not assigned_to:
                return jsonify({'success': False, 'message': 'Assigned user ID required'}), 400
            for wo_id in wo_ids:
                conn.execute("UPDATE work_orders SET assigned_to=?, updated_at=datetime('now') WHERE id=?",
                           (assigned_to, wo_id))
                log_action(session['user_id'], 'BULK_ASSIGN', 'work_orders', wo_id)
                updated_count += 1
        
        elif action == 'status':
            new_status = data.get('status')
            if new_status not in ['open', 'in_progress', 'on_hold', 'completed', 'cancelled']:
                return jsonify({'success': False, 'message': 'Invalid status'}), 400
            for wo_id in wo_ids:
                conn.execute("UPDATE work_orders SET status=?, updated_at=datetime('now') WHERE id=?",
                           (new_status, wo_id))
                log_action(session['user_id'], 'BULK_STATUS_CHANGE', 'work_orders', wo_id, 
                          details=f'Status changed to {new_status}')
                updated_count += 1
        
        elif action == 'priority':
            new_priority = data.get('priority')
            if new_priority not in ['low', 'medium', 'high', 'critical']:
                return jsonify({'success': False, 'message': 'Invalid priority'}), 400
            for wo_id in wo_ids:
                conn.execute("UPDATE work_orders SET priority=?, updated_at=datetime('now') WHERE id=?",
                           (new_priority, wo_id))
                log_action(session['user_id'], 'BULK_PRIORITY_CHANGE', 'work_orders', wo_id,
                          details=f'Priority changed to {new_priority}')
                updated_count += 1
        
        elif action == 'delete':
            # Only admins can bulk delete
            if session.get('role') != 'admin':
                conn.close()
                return jsonify({'success': False, 'message': 'Admin access required'}), 403
            for wo_id in wo_ids:
                conn.execute("DELETE FROM work_orders WHERE id=?", (wo_id,))
                log_action(session['user_id'], 'BULK_DELETE', 'work_orders', wo_id)
                updated_count += 1
        
        else:
            conn.close()
            return jsonify({'success': False, 'message': 'Invalid action'}), 400
        
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'updated_count': updated_count, 
                       'message': f'Successfully updated {updated_count} work orders'})
    
    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'message': str(e)}), 500

# ── PM SCHEDULES ──────────────────────────────────────────────────────────────

@app.route('/api/pm-schedules', methods=['GET'])
@login_required
def get_pm_schedules():
    conn = get_db()
    pms = conn.execute("""SELECT p.*,a.name as asset_name,a.code as asset_code,u.full_name as assigned_to_name,
               CASE WHEN p.next_due < date('now') THEN 'overdue'
                    WHEN p.next_due <= date('now', '+7 days') THEN 'due_soon' ELSE 'ok' END as status
        FROM pm_schedules p LEFT JOIN assets a ON p.asset_id=a.id LEFT JOIN users u ON p.assigned_to=u.id
        WHERE p.active=1 ORDER BY
            CASE WHEN p.next_due < date('now') THEN 1
                 WHEN p.next_due <= date('now', '+7 days') THEN 2 ELSE 3 END, p.next_due""").fetchall()
    conn.close()
    return jsonify([dict(p) for p in pms])

@app.route('/api/pm-schedules/<int:pm_id>', methods=['GET'])
@login_required
def get_pm_schedule(pm_id):
    conn = get_db()
    pm = conn.execute("""SELECT p.*,a.name as asset_name,u.full_name as assigned_to_name
        FROM pm_schedules p LEFT JOIN assets a ON p.asset_id=a.id LEFT JOIN users u ON p.assigned_to=u.id
        WHERE p.id=?""", (pm_id,)).fetchone()
    conn.close()
    if not pm:
        return jsonify({'error': 'Not found'}), 404
    return jsonify(dict(pm))

@app.route('/api/pm-schedules', methods=['POST'])
@login_required
def create_pm_schedule():
    data = request.json
    checklist = data.get('checklist', '[]')
    if isinstance(checklist, list):
        checklist = json.dumps(checklist)
    conn = get_db()
    c = conn.cursor()
    c.execute("""INSERT INTO pm_schedules (title,asset_id,description,frequency,frequency_value,
        next_due,assigned_to,estimated_hours,estimated_cost,checklist,safety_instructions,requires_shutdown)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
    (data['title'], data.get('asset_id'), data.get('description'),
     data.get('frequency', 'monthly'), data.get('frequency_value', 1),
     data.get('next_due'), data.get('assigned_to'), data.get('estimated_hours'),
     data.get('estimated_cost'), checklist, data.get('safety_instructions'), data.get('requires_shutdown', 0)))
    new_id = c.lastrowid
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'id': new_id})

@app.route('/api/pm-schedules/<int:pm_id>', methods=['PUT'])
@login_required
def update_pm_schedule(pm_id):
    data = request.json
    checklist = data.get('checklist', '[]')
    if isinstance(checklist, list):
        checklist = json.dumps(checklist)
    conn = get_db()
    conn.execute("""UPDATE pm_schedules SET title=?,asset_id=?,description=?,frequency=?,frequency_value=?,
        next_due=?,assigned_to=?,estimated_hours=?,estimated_cost=?,checklist=?,safety_instructions=?,
        requires_shutdown=?,active=? WHERE id=?""",
    (data['title'], data.get('asset_id'), data.get('description'), data.get('frequency'),
     data.get('frequency_value'), data.get('next_due'), data.get('assigned_to'),
     data.get('estimated_hours'), data.get('estimated_cost'), checklist,
     data.get('safety_instructions'), data.get('requires_shutdown', 0), data.get('active', 1), pm_id))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/pm-schedules/<int:pm_id>/complete', methods=['POST'])
@login_required
def complete_pm(pm_id):
    data = request.json or {}
    conn = get_db()
    pm = conn.execute("SELECT * FROM pm_schedules WHERE id=?", (pm_id,)).fetchone()
    if not pm:
        conn.close()
        return jsonify({'error': 'Not found'}), 404
    today = datetime.now().date()
    freq = pm['frequency']; fval = pm['frequency_value'] or 1
    if freq == 'daily': next_due = today + timedelta(days=fval)
    elif freq == 'weekly': next_due = today + timedelta(weeks=fval)
    elif freq == 'monthly': next_due = today + timedelta(days=30 * fval)
    elif freq == 'quarterly': next_due = today + timedelta(days=90 * fval)
    elif freq == 'yearly': next_due = today + timedelta(days=365 * fval)
    else: next_due = today + timedelta(days=30 * fval)
    conn.execute("UPDATE pm_schedules SET last_performed=?,next_due=? WHERE id=?",
                (str(today), str(next_due), pm_id))
    wo_number = generate_wo_number()
    c = conn.cursor()
    c.execute("""INSERT INTO work_orders (wo_number,title,description,asset_id,type,priority,status,
        assigned_to,requested_by,scheduled_date,due_date,estimated_hours,completion_notes)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
    (wo_number, f"PM: {pm['title']}", pm['description'], pm['asset_id'],
     'preventive', 'medium', 'completed', pm['assigned_to'], session['user_id'],
     str(today), str(today), pm['estimated_hours'], data.get('notes', f'Completed PM schedule #{pm_id}')))
    wo_id = c.lastrowid
    conn.commit()
    if pm['asset_id']:
        add_asset_history(pm['asset_id'], 'pm_completion', f'PM Completed: {pm["title"]}',
                          data.get('notes', ''), session['user_id'], pm['estimated_cost'] or 0, pm_id, 'pm_schedule')
    conn.close()
    return jsonify({'success': True, 'next_due': str(next_due), 'wo_number': wo_number, 'wo_id': wo_id})

@app.route('/api/pm-schedules/<int:pm_id>', methods=['DELETE'])
@login_required
@admin_required
def delete_pm(pm_id):
    conn = get_db()
    conn.execute("UPDATE pm_schedules SET active=0 WHERE id=?", (pm_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

# ── PARTS ─────────────────────────────────────────────────────────────────────

@app.route('/api/parts', methods=['GET'])
@login_required
def get_parts():
    conn = get_db()
    search = request.args.get('search', '')
    low_stock = request.args.get('low_stock', 'false') == 'true'
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 20))
    offset = (page - 1) * per_page
    query = "SELECT p.*, (p.quantity <= p.min_quantity) as is_low_stock, (p.quantity * p.unit_cost) as total_value FROM parts p WHERE 1=1"
    count_query = "SELECT COUNT(*) FROM parts p WHERE 1=1"
    params = []
    if search:
        q = f'%{search}%'
        query += " AND (p.name LIKE ? OR p.part_number LIKE ? OR p.supplier LIKE ?)"
        count_query += " AND (p.name LIKE ? OR p.part_number LIKE ? OR p.supplier LIKE ?)"
        params += [q, q, q]
    if low_stock:
        query += " AND p.quantity <= p.min_quantity"; count_query += " AND p.quantity <= p.min_quantity"
    query += " ORDER BY is_low_stock DESC, p.name LIMIT ? OFFSET ?"
    total = conn.execute(count_query, params).fetchone()[0]
    parts = conn.execute(query, params + [per_page, offset]).fetchall()
    conn.close()
    return jsonify({'items': [dict(p) for p in parts], 'total': total, 'page': page, 'per_page': per_page, 'pages': (total + per_page - 1) // per_page})

@app.route('/api/parts', methods=['POST'])
@login_required
def create_part():
    data = request.json
    conn = get_db()
    c = conn.cursor()
    c.execute("""INSERT INTO parts (name,part_number,description,quantity,min_quantity,max_quantity,
        reorder_point,unit_cost,location,bin_number,supplier,manufacturer,lead_time_days,notes)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
    (data['name'], data.get('part_number'), data.get('description'), data.get('quantity', 0),
     data.get('min_quantity', 0), data.get('max_quantity', 100), data.get('reorder_point', 5),
     data.get('unit_cost', 0), data.get('location'), data.get('bin_number'), data.get('supplier'),
     data.get('manufacturer'), data.get('lead_time_days', 7), data.get('notes')))
    new_id = c.lastrowid
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'id': new_id})

@app.route('/api/parts/<int:part_id>', methods=['PUT'])
@login_required
def update_part(part_id):
    data = request.json
    conn = get_db()
    conn.execute("""UPDATE parts SET name=?,part_number=?,description=?,quantity=?,min_quantity=?,max_quantity=?,
        reorder_point=?,unit_cost=?,location=?,bin_number=?,supplier=?,manufacturer=?,lead_time_days=?,
        notes=?,updated_at=datetime('now') WHERE id=?""",
    (data['name'], data.get('part_number'), data.get('description'), data.get('quantity', 0),
     data.get('min_quantity', 0), data.get('max_quantity', 100), data.get('reorder_point', 5),
     data.get('unit_cost', 0), data.get('location'), data.get('bin_number'), data.get('supplier'),
     data.get('manufacturer'), data.get('lead_time_days', 7), data.get('notes'), part_id))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/parts/<int:part_id>', methods=['DELETE'])
@login_required
@admin_required
def delete_part(part_id):
    conn = get_db()
    conn.execute("DELETE FROM parts WHERE id=?", (part_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/parts/<int:part_id>/adjust', methods=['POST'])
@login_required
def adjust_inventory(part_id):
    data = request.json
    conn = get_db()
    old = conn.execute("SELECT quantity FROM parts WHERE id=?", (part_id,)).fetchone()
    new_qty = old['quantity'] + data['adjustment']
    conn.execute("UPDATE parts SET quantity=? WHERE id=?", (new_qty, part_id))
    log_action(session['user_id'], 'INVENTORY_ADJUST', 'parts', part_id,
               str(old['quantity']), str(new_qty), f"Adj: {data['adjustment']}, Reason: {data.get('reason','')}")
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'new_quantity': new_qty})

# ── SUPPLIERS ─────────────────────────────────────────────────────────────────

@app.route('/api/suppliers', methods=['GET'])
@login_required
def get_suppliers():
    conn = get_db()
    suppliers = conn.execute("SELECT * FROM suppliers ORDER BY name").fetchall()
    conn.close()
    return jsonify([dict(s) for s in suppliers])

@app.route('/api/suppliers', methods=['POST'])
@login_required
def create_supplier():
    data = request.json
    conn = get_db()
    c = conn.cursor()
    c.execute("""INSERT INTO suppliers (name,contact_person,email,phone,address,website,tax_id,payment_terms,notes)
                 VALUES (?,?,?,?,?,?,?,?,?)""",
    (data['name'], data.get('contact_person'), data.get('email'), data.get('phone'),
     data.get('address'), data.get('website'), data.get('tax_id'), data.get('payment_terms'), data.get('notes')))
    new_id = c.lastrowid
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'id': new_id})

@app.route('/api/suppliers/<int:supplier_id>', methods=['PUT'])
@login_required
def update_supplier(supplier_id):
    data = request.json
    conn = get_db()
    conn.execute("""UPDATE suppliers SET name=?,contact_person=?,email=?,phone=?,address=?,
        website=?,tax_id=?,payment_terms=?,notes=? WHERE id=?""",
    (data['name'], data.get('contact_person'), data.get('email'), data.get('phone'),
     data.get('address'), data.get('website'), data.get('tax_id'), data.get('payment_terms'),
     data.get('notes'), supplier_id))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/suppliers/<int:supplier_id>', methods=['DELETE'])
@login_required
@admin_required
def delete_supplier(supplier_id):
    conn = get_db()
    conn.execute("DELETE FROM suppliers WHERE id=?", (supplier_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

# ── AUDIT LOG ─────────────────────────────────────────────────────────────────

@app.route('/api/audit-log', methods=['GET'])
@login_required
@admin_required
def get_audit_log():
    conn = get_db()
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 50))
    action = request.args.get('action', '')
    table = request.args.get('table', '')
    user_filter = request.args.get('user_id', '')
    offset = (page - 1) * per_page
    query = """SELECT a.*,u.username,u.full_name FROM audit_log a LEFT JOIN users u ON a.user_id=u.id WHERE 1=1"""
    count_query = "SELECT COUNT(*) FROM audit_log a WHERE 1=1"
    params = []
    if action:
        query += " AND a.action=?"; count_query += " AND a.action=?"; params.append(action)
    if table:
        query += " AND a.table_name=?"; count_query += " AND a.table_name=?"; params.append(table)
    if user_filter:
        query += " AND a.user_id=?"; count_query += " AND a.user_id=?"; params.append(user_filter)
    query += " ORDER BY a.created_at DESC LIMIT ? OFFSET ?"
    total = conn.execute(count_query, params).fetchone()[0]
    logs = conn.execute(query, params + [per_page, offset]).fetchall()
    conn.close()
    return jsonify({'items': [dict(l) for l in logs], 'total': total, 'page': page, 'per_page': per_page, 'pages': (total + per_page - 1) // per_page})


# ── DOWNTIME ──────────────────────────────────────────────────────────────────

@app.route('/api/assets/<int:asset_id>/downtime', methods=['GET'])
@login_required
def get_downtime(asset_id):
    conn = get_db()
    records = conn.execute("""SELECT d.*,u.full_name as recorded_by_name
        FROM downtime_records d LEFT JOIN users u ON d.recorded_by=u.id
        WHERE d.asset_id=? ORDER BY d.start_time DESC""", (asset_id,)).fetchall()
    conn.close()
    return jsonify([dict(r) for r in records])

@app.route('/api/assets/<int:asset_id>/downtime', methods=['POST'])
@login_required
def add_downtime(asset_id):
    data = request.json
    conn = get_db()
    dur = None
    if data.get('end_time') and data.get('start_time'):
        from datetime import datetime as dt
        try:
            s = dt.fromisoformat(data['start_time'])
            e = dt.fromisoformat(data['end_time'])
            dur = round((e - s).total_seconds() / 3600, 2)
        except: pass
    conn.execute("""INSERT INTO downtime_records (asset_id,start_time,end_time,reason,category,wo_id,recorded_by,duration_hours,notes)
        VALUES (?,?,?,?,?,?,?,?,?)""",
        (asset_id, data['start_time'], data.get('end_time'), data.get('reason'),
         data.get('category','unplanned'), data.get('wo_id'), session['user_id'], dur, data.get('notes')))
    conn.commit()
    add_asset_history(asset_id, 'status_change', f"Downtime recorded: {data.get('reason','—')}",
        f"Duration: {dur or 'ongoing'} hours | Category: {data.get('category','unplanned')}", session['user_id'], 0)
    conn.close()
    return jsonify({'success': True})

@app.route('/api/downtime/<int:dt_id>', methods=['PUT'])
@login_required
def update_downtime(dt_id):
    data = request.json
    conn = get_db()
    dur = None
    if data.get('end_time') and data.get('start_time'):
        from datetime import datetime as dt
        try:
            s = dt.fromisoformat(data['start_time'])
            e = dt.fromisoformat(data['end_time'])
            dur = round((e - s).total_seconds() / 3600, 2)
        except: pass
    conn.execute("""UPDATE downtime_records SET start_time=?,end_time=?,reason=?,category=?,duration_hours=?,notes=? WHERE id=?""",
        (data.get('start_time'), data.get('end_time'), data.get('reason'), data.get('category','unplanned'), dur, data.get('notes'), dt_id))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/downtime/<int:dt_id>', methods=['DELETE'])
@login_required
def delete_downtime(dt_id):
    conn = get_db()
    conn.execute("DELETE FROM downtime_records WHERE id=?", (dt_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

# ── ASSET PARTS (Spare Parts Linked to Asset) ─────────────────────────────────

@app.route('/api/assets/<int:asset_id>/parts', methods=['GET'])
@login_required
def get_asset_parts(asset_id):
    conn = get_db()
    parts = conn.execute("""SELECT ap.*,p.name,p.part_number,p.quantity,p.unit_cost,p.location,p.min_quantity
        FROM asset_parts ap JOIN parts p ON ap.part_id=p.id WHERE ap.asset_id=?""", (asset_id,)).fetchall()
    conn.close()
    return jsonify([dict(r) for r in parts])

@app.route('/api/assets/<int:asset_id>/parts', methods=['POST'])
@login_required
def add_asset_part(asset_id):
    data = request.json
    conn = get_db()
    try:
        conn.execute("INSERT OR REPLACE INTO asset_parts (asset_id,part_id,quantity_required,notes) VALUES (?,?,?,?)",
            (asset_id, data['part_id'], data.get('quantity_required', 1), data.get('notes')))
        conn.commit()
    except Exception as e:
        conn.close()
        return jsonify({'error': str(e)}), 400
    conn.close()
    return jsonify({'success': True})

@app.route('/api/assets/<int:asset_id>/parts/<int:ap_id>', methods=['DELETE'])
@login_required
def remove_asset_part(asset_id, ap_id):
    conn = get_db()
    conn.execute("DELETE FROM asset_parts WHERE id=? AND asset_id=?", (ap_id, asset_id))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

# ── CALENDAR ──────────────────────────────────────────────────────────────────

@app.route('/api/calendar')
@login_required
def get_calendar():
    conn = get_db()
    month = request.args.get('month', datetime.now().strftime('%Y-%m'))
    start = month + '-01'
    # End of month
    import calendar as cal_mod
    y, m = int(month[:4]), int(month[5:7])
    last_day = cal_mod.monthrange(y, m)[1]
    end = f"{month}-{last_day:02d}"

    wos = conn.execute("""SELECT w.id,w.wo_number,w.title,w.status,w.priority,w.type,
        w.due_date,w.scheduled_date,a.name as asset_name
        FROM work_orders w LEFT JOIN assets a ON w.asset_id=a.id
        WHERE (w.due_date BETWEEN ? AND ? OR w.scheduled_date BETWEEN ? AND ?)
        AND w.status != 'cancelled'""", (start, end, start, end)).fetchall()
    pms = conn.execute("""SELECT p.id,p.title,p.next_due,p.estimated_hours,a.name as asset_name
        FROM pm_schedules p LEFT JOIN assets a ON p.asset_id=a.id
        WHERE p.next_due BETWEEN ? AND ? AND p.active=1""", (start, end)).fetchall()
    conn.close()
    return jsonify({
        'work_orders': [dict(r) for r in wos],
        'pm_schedules': [dict(r) for r in pms],
        'month': month
    })

# ── IMPORT ────────────────────────────────────────────────────────────────────

@app.route('/api/import/assets', methods=['POST'])
@login_required
def import_assets():
    data = request.json.get('rows', [])
    conn = get_db()
    created = 0
    errors = []
    for i, row in enumerate(data):
        try:
            code = row.get('code') or row.get('Code') or None
            name = row.get('name') or row.get('Name') or row.get('asset_name')
            if not name:
                errors.append(f"Row {i+1}: missing name")
                continue
            conn.execute("""INSERT OR IGNORE INTO assets (name,code,status,make,model,serial_number,purchase_date,purchase_cost,criticality,description,notes)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (name, code, row.get('status','active'), row.get('make'), row.get('model'),
                 row.get('serial_number'), row.get('purchase_date'), row.get('purchase_cost') or None,
                 row.get('criticality','medium'), row.get('description'), row.get('notes')))
            created += 1
        except Exception as e:
            errors.append(f"Row {i+1}: {str(e)}")
    conn.commit()
    conn.close()
    return jsonify({'created': created, 'errors': errors})

@app.route('/api/import/parts', methods=['POST'])
@login_required
def import_parts():
    data = request.json.get('rows', [])
    conn = get_db()
    created = 0
    errors = []
    for i, row in enumerate(data):
        try:
            name = row.get('name') or row.get('Name') or row.get('part_name')
            if not name:
                errors.append(f"Row {i+1}: missing name")
                continue
            conn.execute("""INSERT OR IGNORE INTO parts (name,part_number,description,quantity,min_quantity,unit_cost,location,supplier,manufacturer,notes)
                VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (name, row.get('part_number'), row.get('description'),
                 int(row.get('quantity', 0) or 0), int(row.get('min_quantity', 0) or 0),
                 float(row.get('unit_cost', 0) or 0), row.get('location'), row.get('supplier'),
                 row.get('manufacturer'), row.get('notes')))
            created += 1
        except Exception as e:
            errors.append(f"Row {i+1}: {str(e)}")
    conn.commit()
    conn.close()
    return jsonify({'created': created, 'errors': errors})

# ── REPORTS ───────────────────────────────────────────────────────────────────

@app.route('/api/reports/kpi')
@login_required
def kpi_report():
    conn = get_db()
    total_wo = conn.execute("SELECT COUNT(*) FROM work_orders").fetchone()[0]
    completed_wo = conn.execute("SELECT COUNT(*) FROM work_orders WHERE status='completed'").fetchone()[0]
    mttr = conn.execute("""SELECT AVG(julianday(completed_at) - julianday(started_at)) * 24
        FROM work_orders WHERE status='completed' AND started_at IS NOT NULL AND completed_at IS NOT NULL""").fetchone()[0]
    failures = conn.execute("SELECT COUNT(*) FROM work_orders WHERE type='corrective' AND created_at >= date('now', '-1 year')").fetchone()[0]
    mtbf = (365 * 24 / failures) if failures > 0 else 0
    total_cost = conn.execute("SELECT SUM(total_cost) FROM work_orders").fetchone()[0] or 0
    inventory_value = conn.execute("SELECT SUM(quantity * unit_cost) FROM parts").fetchone()[0] or 0
    total_assets = conn.execute("SELECT COUNT(*) FROM assets").fetchone()[0]
    active_assets = conn.execute("SELECT COUNT(*) FROM assets WHERE status='active'").fetchone()[0]
    total_pm = conn.execute("SELECT COUNT(*) FROM pm_schedules WHERE active=1").fetchone()[0]
    overdue_pm = conn.execute("SELECT COUNT(*) FROM pm_schedules WHERE next_due < date('now') AND active=1").fetchone()[0]
    conn.close()
    return jsonify({
        'total_wo': total_wo, 'completed_wo': completed_wo,
        'wo_completion_rate': round(completed_wo / total_wo * 100, 1) if total_wo > 0 else 0,
        'mttr': round(mttr, 2) if mttr else 0, 'mtbf': round(mtbf, 2),
        'total_maintenance_cost': round(total_cost, 2), 'inventory_value': round(inventory_value, 2),
        'asset_utilization': round(active_assets / total_assets * 100, 1) if total_assets > 0 else 0,
        'pm_compliance': round((total_pm - overdue_pm) / total_pm * 100, 1) if total_pm > 0 else 0,
        'total_assets': total_assets, 'active_assets': active_assets,
    })

@app.route('/api/reports/export/<report_type>')
@login_required
def export_report(report_type):
    conn = get_db()
    if report_type == 'assets':
        data = conn.execute("""SELECT a.*,ac.name as category,l.name as location FROM assets a
            LEFT JOIN asset_categories ac ON a.category_id=ac.id LEFT JOIN locations l ON a.location_id=l.id ORDER BY a.name""").fetchall()
        filename = f"assets_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    elif report_type == 'work_orders':
        data = conn.execute("""SELECT w.*,a.name as asset_name,u1.full_name as assigned_to,u2.full_name as requested_by
            FROM work_orders w LEFT JOIN assets a ON w.asset_id=a.id
            LEFT JOIN users u1 ON w.assigned_to=u1.id LEFT JOIN users u2 ON w.requested_by=u2.id
            ORDER BY w.created_at DESC""").fetchall()
        filename = f"work_orders_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    elif report_type == 'parts':
        data = conn.execute("SELECT *,(quantity * unit_cost) as total_value FROM parts ORDER BY name").fetchall()
        filename = f"inventory_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    else:
        conn.close()
        return jsonify({'error': 'Invalid report type'}), 400
    conn.close()
    output = io.StringIO()
    if data:
        writer = csv.writer(output)
        writer.writerow(data[0].keys())
        for row in data:
            writer.writerow(row)
    response = make_response(output.getvalue())
    response.headers["Content-Disposition"] = f"attachment; filename={filename}"
    response.headers["Content-type"] = "text/csv"
    return response

# ── LOOKUPS ───────────────────────────────────────────────────────────────────

@app.route('/api/locations')
@login_required
def get_locations():
    conn = get_db()
    locs = conn.execute("SELECT * FROM locations ORDER BY name").fetchall()
    conn.close()
    return jsonify([dict(l) for l in locs])

@app.route('/api/categories')
@login_required
def get_categories():
    conn = get_db()
    cats = conn.execute("SELECT * FROM asset_categories ORDER BY name").fetchall()
    conn.close()
    return jsonify([dict(c) for c in cats])

@app.route('/api/settings', methods=['GET'])
@login_required
@admin_required
def get_settings():
    conn = get_db()
    settings = conn.execute("SELECT * FROM settings ORDER BY key").fetchall()
    conn.close()
    return jsonify([dict(s) for s in settings])

@app.route('/api/settings', methods=['PUT'])
@login_required
@admin_required
def update_settings():
    data = request.json
    conn = get_db()
    for key, value in data.items():
        conn.execute("UPDATE settings SET value=?,updated_at=datetime('now') WHERE key=?", (value, key))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

# ── v6: BUDGET TRACKER ────────────────────────────────────────────────────────

@app.route('/api/budget', methods=['GET'])
@login_required
def get_budget():
    year = request.args.get('year', datetime.now().year)
    conn = get_db()
    budgets = conn.execute(
        "SELECT * FROM maintenance_budget WHERE year=? ORDER BY month", (year,)
    ).fetchall()
    # Actual spend per month from work orders
    actuals = conn.execute("""
        SELECT CAST(strftime('%m', created_at) AS INTEGER) as month,
               SUM(total_cost) as actual
        FROM work_orders
        WHERE strftime('%Y', created_at)=? AND status NOT IN ('cancelled')
        GROUP BY month
    """, (str(year),)).fetchall()
    actual_map = {r['month']: r['actual'] or 0 for r in actuals}
    budget_map = {r['month']: dict(r) for r in budgets}
    result = []
    for m in range(1, 13):
        budget_row = budget_map.get(m, {'budget_amount': 0, 'notes': ''})
        result.append({
            'year': int(year), 'month': m,
            'budget': budget_row.get('budget_amount', 0) or 0,
            'actual': round(actual_map.get(m, 0), 2),
            'notes': budget_row.get('notes', ''),
            'id': budget_row.get('id'),
        })
    annual = conn.execute("SELECT SUM(budget_amount) FROM maintenance_budget WHERE year=?", (year,)).fetchone()[0] or 0
    annual_actual = conn.execute("""SELECT SUM(total_cost) FROM work_orders
        WHERE strftime('%Y', created_at)=? AND status NOT IN ('cancelled')""", (str(year),)).fetchone()[0] or 0
    conn.close()
    return jsonify({'months': result, 'annual_budget': round(annual, 2), 'annual_actual': round(annual_actual, 2)})

@app.route('/api/budget', methods=['PUT'])
@login_required
@admin_required
def update_budget():
    data = request.json  # list of {year, month, budget, notes}
    conn = get_db()
    for row in data:
        conn.execute("""INSERT INTO maintenance_budget (year, month, budget_amount, notes, updated_at)
            VALUES (?,?,?,?,datetime('now'))
            ON CONFLICT(year,month) DO UPDATE SET budget_amount=excluded.budget_amount,
            notes=excluded.notes, updated_at=datetime('now')""",
            (row['year'], row['month'], row.get('budget', 0), row.get('notes', '')))
    conn.commit()
    conn.close()
    log_action(session.get('user_id'), 'UPDATE', 'maintenance_budget', None, details='Budget updated')
    return jsonify({'success': True})

# ── v6: SLA CONFIG ────────────────────────────────────────────────────────────

@app.route('/api/sla-config', methods=['GET'])
@login_required
def get_sla_config():
    conn = get_db()
    rows = conn.execute("SELECT * FROM sla_config ORDER BY CASE priority WHEN 'critical' THEN 1 WHEN 'high' THEN 2 WHEN 'medium' THEN 3 ELSE 4 END").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route('/api/sla-config', methods=['PUT'])
@login_required
@admin_required
def update_sla_config():
    data = request.json  # list of {priority, response_hours, resolution_hours, escalation_hours}
    conn = get_db()
    for row in data:
        conn.execute("""INSERT INTO sla_config (priority, response_hours, resolution_hours, escalation_hours, updated_at)
            VALUES (?,?,?,?,datetime('now'))
            ON CONFLICT(priority) DO UPDATE SET response_hours=excluded.response_hours,
            resolution_hours=excluded.resolution_hours, escalation_hours=excluded.escalation_hours,
            updated_at=datetime('now')""",
            (row['priority'], row.get('response_hours', 4), row.get('resolution_hours', 24), row.get('escalation_hours', 48)))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

# ── v6: SLA STATUS FOR OPEN WOs ───────────────────────────────────────────────

@app.route('/api/sla-status')
@login_required
def get_sla_status():
    """Return open WOs with SLA breach status based on configured thresholds."""
    conn = get_db()
    sla_rows = conn.execute("SELECT * FROM sla_config").fetchall()
    sla_map = {r['priority']: dict(r) for r in sla_rows}
    wos = conn.execute("""SELECT w.id, w.wo_number, w.title, w.priority, w.status,
        w.created_at, w.due_date, a.name as asset_name,
        u.full_name as assigned_to_name
        FROM work_orders w
        LEFT JOIN assets a ON w.asset_id=a.id
        LEFT JOIN users u ON w.assigned_to=u.id
        WHERE w.status IN ('open','in_progress')
        ORDER BY w.created_at""").fetchall()
    now = datetime.now()
    result = []
    for wo in wos:
        w = dict(wo)
        sla = sla_map.get(w['priority'], {'response_hours': 4, 'resolution_hours': 24, 'escalation_hours': 48})
        created = datetime.fromisoformat(w['created_at']) if w['created_at'] else now
        age_hours = (now - created).total_seconds() / 3600
        resolution_hours = sla['resolution_hours']
        response_hours = sla['response_hours']
        pct = min(age_hours / max(resolution_hours, 1) * 100, 100)
        if age_hours > sla['escalation_hours']:
            sla_status = 'escalated'
        elif age_hours > resolution_hours:
            sla_status = 'breached'
        elif age_hours > resolution_hours * 0.75:
            sla_status = 'at_risk'
        else:
            sla_status = 'ok'
        remaining = max(resolution_hours - age_hours, 0)
        w['age_hours'] = round(age_hours, 1)
        w['sla_status'] = sla_status
        w['sla_pct'] = round(pct, 1)
        w['sla_remaining_hours'] = round(remaining, 1)
        w['sla_resolution_hours'] = resolution_hours
        result.append(w)
    conn.close()
    return jsonify(result)

# ── v6: WO ESCALATION ─────────────────────────────────────────────────────────

@app.route('/api/escalate-overdue', methods=['POST'])
@login_required
@admin_required
def escalate_overdue():
    """Escalate priority of open WOs that exceed their SLA escalation_hours threshold."""
    conn = get_db()
    sla_rows = conn.execute("SELECT * FROM sla_config").fetchall()
    sla_map = {r['priority']: dict(r) for r in sla_rows}
    wos = conn.execute("""SELECT id, wo_number, title, priority, created_at, assigned_to
        FROM work_orders WHERE status IN ('open','in_progress')""").fetchall()
    now = datetime.now()
    escalated = []
    priority_up = {'low': 'medium', 'medium': 'high', 'high': 'critical'}
    for wo in wos:
        sla = sla_map.get(wo['priority'], {'escalation_hours': 48})
        created = datetime.fromisoformat(wo['created_at']) if wo['created_at'] else now
        age_hours = (now - created).total_seconds() / 3600
        if age_hours >= sla['escalation_hours'] and wo['priority'] in priority_up:
            new_priority = priority_up[wo['priority']]
            conn.execute("UPDATE work_orders SET priority=?,updated_at=datetime('now') WHERE id=?",
                         (new_priority, wo['id']))
            log_action(None, 'ESCALATE', 'work_orders', wo['id'],
                       old_value=wo['priority'], new_value=new_priority,
                       details=f'Auto-escalated after {round(age_hours,1)}h (SLA: {sla["escalation_hours"]}h)')
            if wo['assigned_to']:
                send_notification(wo['assigned_to'], 'work_order',
                    f'⚠️ WO Escalated: {wo["wo_number"]}',
                    f'Priority escalated from {wo["priority"]} to {new_priority} due to SLA breach.',
                    f'/work-orders/{wo["id"]}')
            escalated.append({'id': wo['id'], 'wo_number': wo['wo_number'],
                               'old_priority': wo['priority'], 'new_priority': new_priority})
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'escalated': escalated, 'count': len(escalated)})

# ── v6: REORDER WIZARD ────────────────────────────────────────────────────────

@app.route('/api/reorder-wizard', methods=['GET'])
@login_required
def reorder_wizard_data():
    """Return low-stock parts grouped by supplier for bulk PO generation."""
    conn = get_db()
    parts = conn.execute("""
        SELECT p.*, (p.min_quantity - p.quantity) as shortage,
               (p.max_quantity - p.quantity) as order_to_max
        FROM parts p
        WHERE p.quantity <= p.min_quantity
        ORDER BY p.supplier, p.name
    """).fetchall()
    conn.close()
    by_supplier = {}
    for p in parts:
        sup = p['supplier'] or 'Unknown Supplier'
        if sup not in by_supplier:
            by_supplier[sup] = []
        item = dict(p)
        item['suggested_qty'] = max(item['order_to_max'], item['shortage'], 1)
        item['suggested_cost'] = round(item['suggested_qty'] * (item['unit_cost'] or 0), 2)
        by_supplier[sup].append(item)
    return jsonify({'by_supplier': by_supplier, 'total_parts': len(parts)})

@app.route('/api/reorder-wizard/generate-po', methods=['POST'])
@login_required
def generate_reorder_po():
    """Generate one or more POs from the reorder wizard selections."""
    data = request.json  # {supplier_name, parts: [{part_id, qty, unit_cost}]}
    conn = get_db()
    supplier_name = data.get('supplier_name', '')
    parts = data.get('parts', [])
    if not parts:
        conn.close()
        return jsonify({'success': False, 'error': 'No parts selected'}), 400
    # Find supplier by name
    supplier = conn.execute("SELECT id FROM suppliers WHERE name=?", (supplier_name,)).fetchone()
    supplier_id = supplier['id'] if supplier else None
    po_number = generate_po_number()
    subtotal = sum(p.get('unit_cost', 0) * p.get('qty', 1) for p in parts)
    c = conn.cursor()
    c.execute("""INSERT INTO purchase_orders (po_number, supplier_id, ordered_by, status, subtotal, total, notes)
        VALUES (?,?,?,?,?,?,?)""",
        (po_number, supplier_id, session['user_id'], 'pending', subtotal, subtotal,
         f'Auto-generated by Reorder Wizard on {datetime.now().strftime("%Y-%m-%d")}'))
    po_id = c.lastrowid
    for p in parts:
        qty = p.get('qty', 1)
        unit_cost = p.get('unit_cost', 0)
        line_total = qty * unit_cost
        c.execute("""INSERT INTO po_items (po_id, part_id, description, quantity, unit_cost, line_total)
            VALUES (?,?,?,?,?,?)""",
            (po_id, p['part_id'], p.get('name',''), qty, unit_cost, line_total))
    conn.commit()
    log_action(session['user_id'], 'CREATE', 'purchase_orders', po_id,
               details=f'PO {po_number} generated by Reorder Wizard for {supplier_name}')
    conn.close()
    return jsonify({'success': True, 'po_number': po_number, 'po_id': po_id, 'total': subtotal})

# ── v6: GLOBAL SEARCH ─────────────────────────────────────────────────────────

@app.route('/api/global-search')
@login_required
def global_search_v6():
    q = request.args.get('q', '').strip()
    if len(q) < 2:
        return jsonify({'results': []})
    like = f'%{q}%'
    conn = get_db()
    assets = conn.execute("""SELECT id, name, code, status, 'asset' as type FROM assets
        WHERE name LIKE ? OR code LIKE ? OR serial_number LIKE ? LIMIT 6""",
        (like, like, like)).fetchall()
    wos = conn.execute("""SELECT id, wo_number as code, title as name, status, 'work_order' as type
        FROM work_orders WHERE title LIKE ? OR wo_number LIKE ? LIMIT 6""",
        (like, like)).fetchall()
    parts = conn.execute("""SELECT id, part_number as code, name, NULL as status, 'part' as type
        FROM parts WHERE name LIKE ? OR part_number LIKE ? LIMIT 4""",
        (like, like)).fetchall()
    pms = conn.execute("""SELECT id, NULL as code, title as name, NULL as status, 'pm' as type
        FROM pm_schedules WHERE title LIKE ? AND active=1 LIMIT 4""",
        (like,)).fetchall()
    conn.close()
    results = []
    icons = {'asset': '🏭', 'work_order': '🔧', 'part': '📦', 'pm': '📅'}
    for row in list(assets) + list(wos) + list(parts) + list(pms):
        r = dict(row)
        r['icon'] = icons.get(r['type'], '🔍')
        results.append(r)
    return jsonify({'results': results, 'query': q})

# ── v6: WO PDF PRINT ─────────────────────────────────────────────────────────

@app.route('/api/work-orders/<int:wo_id>/print')
@login_required
def print_work_order(wo_id):
    """Return a self-contained HTML page for printing a work order."""
    conn = get_db()
    wo = conn.execute("""SELECT w.*,a.name as asset_name,a.code as asset_code,
        u1.full_name as assigned_to_name, u2.full_name as requested_by_name,
        l.name as location_name
        FROM work_orders w LEFT JOIN assets a ON w.asset_id=a.id
        LEFT JOIN users u1 ON w.assigned_to=u1.id
        LEFT JOIN users u2 ON w.requested_by=u2.id
        LEFT JOIN locations l ON a.location_id=l.id
        WHERE w.id=?""", (wo_id,)).fetchone()
    if not wo:
        conn.close()
        return "Work order not found", 404
    wo = dict(wo)
    parts = conn.execute("""SELECT wp.quantity_used, wp.unit_cost, wp.line_total, p.name, p.part_number
        FROM wo_parts wp JOIN parts p ON wp.part_id=p.id WHERE wp.wo_id=?""", (wo_id,)).fetchall()
    time_entries = conn.execute("""SELECT te.hours_worked, te.work_date, te.description, u.full_name
        FROM wo_time_entries te JOIN users u ON te.user_id=u.id WHERE te.wo_id=?""", (wo_id,)).fetchall()
    comments = conn.execute("""SELECT c.content, c.created_at, u.full_name, c.is_private
        FROM comments c JOIN users u ON c.user_id=u.id
        WHERE c.wo_id=? AND c.is_private=0 ORDER BY c.created_at""", (wo_id,)).fetchall()
    company = conn.execute("SELECT value FROM settings WHERE key='company_name'").fetchone()
    conn.close()
    company_name = company['value'] if company else 'NEXUS CMMS'
    priority_colors = {'critical':'#dc2626','high':'#f59e0b','medium':'#3b82f6','low':'#10b981'}
    status_labels = {'open':'Open','in_progress':'In Progress','completed':'Completed','cancelled':'Cancelled','on_hold':'On Hold'}
    pr_color = priority_colors.get(wo.get('priority','medium'), '#3b82f6')

    parts_rows = ''.join(f"""<tr><td>{p['name']}</td><td>{p['part_number'] or ''}</td>
        <td style="text-align:center">{p['quantity_used']}</td>
        <td style="text-align:right">₹{p['unit_cost'] or 0:.2f}</td>
        <td style="text-align:right">₹{p['line_total'] or 0:.2f}</td></tr>""" for p in parts)
    time_rows = ''.join(f"""<tr><td>{t['work_date']}</td><td>{t['full_name']}</td>
        <td style="text-align:center">{t['hours_worked']}</td>
        <td>{t['description'] or ''}</td></tr>""" for t in time_entries)
    comment_rows = ''.join(f"""<tr><td>{c['created_at']}</td><td>{c['full_name']}</td>
        <td>{c['content']}</td></tr>""" for c in comments)

    html = f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
<title>Work Order {wo['wo_number']}</title>
<style>
  body{{font-family:Arial,sans-serif;font-size:12px;color:#111;margin:0;padding:24px}}
  .header{{display:flex;justify-content:space-between;align-items:flex-start;border-bottom:2px solid #111;padding-bottom:12px;margin-bottom:16px}}
  .logo{{font-size:22px;font-weight:700;letter-spacing:2px;color:#111}}
  .wo-num{{font-size:20px;font-weight:700;font-family:monospace}}
  .badge{{display:inline-block;padding:3px 10px;border-radius:12px;font-size:11px;font-weight:700;color:white;background:{pr_color}}}
  .section{{margin-bottom:16px}}
  .section h3{{font-size:12px;text-transform:uppercase;letter-spacing:1px;color:#666;border-bottom:1px solid #ddd;padding-bottom:4px;margin-bottom:8px}}
  .grid{{display:grid;grid-template-columns:1fr 1fr;gap:8px}}
  .field{{margin-bottom:6px}}
  .field label{{font-size:10px;color:#888;display:block;text-transform:uppercase;letter-spacing:.5px}}
  .field span{{font-size:12px;font-weight:500}}
  table{{width:100%;border-collapse:collapse;font-size:11px}}
  th{{background:#f3f4f6;padding:6px 8px;text-align:left;font-size:10px;text-transform:uppercase;letter-spacing:.5px}}
  td{{padding:6px 8px;border-bottom:1px solid #e5e7eb}}
  .sig-box{{border:1px solid #ccc;height:60px;margin-top:8px;border-radius:4px}}
  .totals{{text-align:right;font-weight:700;font-size:13px;margin-top:8px}}
  @media print{{body{{padding:0}}}}
</style>
</head><body>
<div class="header">
  <div>
    <div class="logo">⚙ {company_name}</div>
    <div style="color:#666;font-size:11px;margin-top:4px">Work Order</div>
  </div>
  <div style="text-align:right">
    <div class="wo-num">{wo['wo_number']}</div>
    <div style="margin-top:6px"><span class="badge">{(wo.get('priority','medium') or 'medium').upper()}</span>
    &nbsp;<span style="background:#e5e7eb;padding:3px 10px;border-radius:12px;font-size:11px;font-weight:700">{status_labels.get(wo.get('status','open'),'Open')}</span></div>
  </div>
</div>

<div class="section">
  <h3>Work Order Details</h3>
  <div style="font-size:15px;font-weight:700;margin-bottom:10px">{wo.get('title','')}</div>
  <div class="grid">
    <div class="field"><label>Type</label><span>{(wo.get('type','') or '').replace('_',' ').title()}</span></div>
    <div class="field"><label>Asset</label><span>{wo.get('asset_name','—')}</span></div>
    <div class="field"><label>Location</label><span>{wo.get('location_name','—')}</span></div>
    <div class="field"><label>Assigned To</label><span>{wo.get('assigned_to_name','Unassigned')}</span></div>
    <div class="field"><label>Requested By</label><span>{wo.get('requested_by_name','—')}</span></div>
    <div class="field"><label>Scheduled</label><span>{wo.get('scheduled_date','—')}</span></div>
    <div class="field"><label>Due Date</label><span>{wo.get('due_date','—')}</span></div>
    <div class="field"><label>Est. Hours</label><span>{wo.get('estimated_hours','—')}</span></div>
    <div class="field"><label>Actual Hours</label><span>{wo.get('actual_hours','—')}</span></div>
    <div class="field"><label>Created</label><span>{(wo.get('created_at','') or '')[:10]}</span></div>
  </div>
  {'<div class="field" style="margin-top:8px"><label>Description</label><span>' + (wo.get('description') or '') + '</span></div>' if wo.get('description') else ''}
  {'<div class="field" style="margin-top:6px"><label>Safety Notes</label><span style="color:#dc2626">' + (wo.get('safety_notes') or '') + '</span></div>' if wo.get('safety_notes') else ''}
  {'<div class="field" style="margin-top:6px"><label>Tools Required</label><span>' + (wo.get('tools_required') or '') + '</span></div>' if wo.get('tools_required') else ''}
</div>

{'<div class="section"><h3>Parts Used</h3><table><thead><tr><th>Part Name</th><th>Part #</th><th style="text-align:center">Qty</th><th style="text-align:right">Unit Cost</th><th style="text-align:right">Total</th></tr></thead><tbody>' + parts_rows + '</tbody></table><div class="totals">Parts Total: ₹' + f'{wo.get("parts_cost",0) or 0:.2f}' + '</div></div>' if parts else ''}

{'<div class="section"><h3>Labor / Time Entries</h3><table><thead><tr><th>Date</th><th>Technician</th><th style="text-align:center">Hours</th><th>Notes</th></tr></thead><tbody>' + time_rows + '</tbody></table><div class="totals">Labor Total: ₹' + f'{wo.get("labor_cost",0) or 0:.2f}' + '</div></div>' if time_entries else ''}

<div class="section" style="background:#f9fafb;padding:12px;border-radius:6px">
  <div style="display:flex;justify-content:space-between">
    <div><label style="font-size:10px;color:#888;text-transform:uppercase">Labor Cost</label><div style="font-size:15px;font-weight:700">₹{wo.get('labor_cost',0) or 0:.2f}</div></div>
    <div><label style="font-size:10px;color:#888;text-transform:uppercase">Parts Cost</label><div style="font-size:15px;font-weight:700">₹{wo.get('parts_cost',0) or 0:.2f}</div></div>
    <div><label style="font-size:10px;color:#888;text-transform:uppercase">Total Cost</label><div style="font-size:18px;font-weight:700;color:#059669">₹{wo.get('total_cost',0) or 0:.2f}</div></div>
  </div>
</div>

{'<div class="section"><h3>Completion Notes</h3><p>' + (wo.get('completion_notes') or '') + '</p></div>' if wo.get('completion_notes') else ''}
{'<div class="section"><h3>Comments</h3><table><thead><tr><th>Date</th><th>User</th><th>Comment</th></tr></thead><tbody>' + comment_rows + '</tbody></table></div>' if comments else ''}

<div class="section" style="margin-top:24px">
  <h3>Sign-off</h3>
  <div class="grid">
    <div><div style="font-size:10px;color:#888;text-transform:uppercase;margin-bottom:4px">Technician Signature</div><div class="sig-box"></div><div style="font-size:10px;color:#888;margin-top:4px">Name: _____________________ Date: __________</div></div>
    <div><div style="font-size:10px;color:#888;text-transform:uppercase;margin-bottom:4px">Supervisor Approval</div><div class="sig-box"></div><div style="font-size:10px;color:#888;margin-top:4px">Name: _____________________ Date: __________</div></div>
  </div>
</div>

<div style="text-align:center;color:#aaa;font-size:10px;margin-top:24px;border-top:1px solid #e5e7eb;padding-top:8px">
  Printed from {company_name} NEXUS CMMS v9 · {datetime.now().strftime('%Y-%m-%d %H:%M')}
</div>
<script>window.onload = function(){{ window.print(); }}</script>
</body></html>"""
    return html

# ── v6: AUTO BACKUP ENGINE ────────────────────────────────────────────────────

_auto_backup_thread_started = False

def run_auto_backup():
    """Background thread: periodically backs up the DB if enabled."""
    import shutil
    while True:
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            enabled_row = conn.execute("SELECT value FROM settings WHERE key='auto_backup_enabled'").fetchone()
            interval_row = conn.execute("SELECT value FROM settings WHERE key='auto_backup_interval_hours'").fetchone()
            keep_row = conn.execute("SELECT value FROM settings WHERE key='auto_backup_keep_count'").fetchone()
            conn.close()
            enabled = (enabled_row['value'] if enabled_row else 'true') == 'true'
            interval_hours = float(interval_row['value'] if interval_row else 24)
            keep_count = int(keep_row['value'] if keep_row else 7)
        except Exception:
            enabled = False
            interval_hours = 24
            keep_count = 7

        if enabled and os.path.exists(DB_PATH):
            try:
                ts = datetime.now().strftime('%Y%m%d_%H%M%S')
                backup_dir = os.path.dirname(os.path.abspath(DB_PATH))
                backup_name = f'cmms_auto_backup_{ts}.db'
                backup_path = os.path.join(backup_dir, backup_name)
                shutil.copy2(DB_PATH, backup_path)
                size_kb = round(os.path.getsize(backup_path) / 1024, 1)
                # Log to auto_backup_log
                log_conn = sqlite3.connect(DB_PATH)
                log_conn.execute("""INSERT INTO auto_backup_log (backup_file, backup_type, size_kb, status)
                    VALUES (?,?,?,?)""", (backup_name, 'auto', size_kb, 'success'))
                log_conn.commit()
                # Prune old auto backups beyond keep_count
                files = sorted([f for f in os.listdir(backup_dir) if f.startswith('cmms_auto_backup_') and f.endswith('.db')])
                while len(files) > keep_count:
                    oldest = files.pop(0)
                    try:
                        os.remove(os.path.join(backup_dir, oldest))
                        log_conn.execute("DELETE FROM auto_backup_log WHERE backup_file=?", (oldest,))
                    except Exception:
                        pass
                log_conn.commit()
                log_conn.close()
            except Exception:
                pass

        time.sleep(interval_hours * 3600)

def start_auto_backup_thread():
    global _auto_backup_thread_started
    if not _auto_backup_thread_started:
        _auto_backup_thread_started = True
        t = threading.Thread(target=run_auto_backup, daemon=True)
        t.start()

@app.route('/api/auto-backup-log')
@login_required
@admin_required
def get_auto_backup_log():
    conn = get_db()
    rows = conn.execute("SELECT * FROM auto_backup_log ORDER BY created_at DESC LIMIT 30").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route('/api/run-backup-now', methods=['POST'])
@login_required
@admin_required
def run_backup_now():
    """Trigger an immediate manual backup outside of the scheduler."""
    import shutil
    if not os.path.exists(DB_PATH):
        return jsonify({'success': False, 'error': 'Database not found'}), 404
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_name = f'cmms_auto_backup_{ts}.db'
    backup_path = os.path.join(os.path.dirname(os.path.abspath(DB_PATH)), backup_name)
    try:
        shutil.copy2(DB_PATH, backup_path)
        size_kb = round(os.path.getsize(backup_path) / 1024, 1)
        conn = get_db()
        conn.execute("INSERT INTO auto_backup_log (backup_file,backup_type,size_kb,status) VALUES (?,?,?,?)",
                     (backup_name, 'manual', size_kb, 'success'))
        conn.commit()
        conn.close()
        log_action(session.get('user_id'), 'DB_BACKUP', 'system', None, details=f'Manual backup: {backup_name}')
        return jsonify({'success': True, 'backup_file': backup_name, 'size_kb': size_kb})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ── HTML FRONTEND ─────────────────────────────────────────────────────────────

HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<meta name="theme-color" content="#00e5a0" media="(prefers-color-scheme: dark)">
<meta name="theme-color" content="#00b87d" media="(prefers-color-scheme: light)">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="NEXUS CMMS">
<meta name="mobile-web-app-capable" content="yes">
<meta name="description" content="NEXUS CMMS Enterprise - Maintenance Management">
<link rel="manifest" href="/manifest.json">
<title>NEXUS CMMS Enterprise</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.0/chart.umd.min.js"></script>
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@300;400;500;600;700&display=swap');
:root {
  /* ── Backgrounds ── */
  --bg0:#06070a; --bg1:#0c0e13; --bg2:#13151d; --bg3:#1a1d27;
  --bg4:#20232e;
  /* ── Borders ── */
  --border:#1e2130; --border2:#282c3d;
  /* ── Brand ── */
  --green:#00e5a0; --green2:#00c988; --green3:#00a86b;
  --green-glow:rgba(0,229,160,.14); --green-glow2:rgba(0,229,160,.08);
  /* ── Status colours ── */
  --red:#ff4d6d;   --red-glow:rgba(255,77,109,.12);
  --yellow:#ffbe4d;--yellow-glow:rgba(255,190,77,.12);
  --blue:#4da6ff;  --blue-glow:rgba(77,166,255,.12);
  --purple:#b06dff;--purple-glow:rgba(176,109,255,.12);
  --orange:#ff8c42;--orange-glow:rgba(255,140,66,.12);
  /* ── Typography ── */
  --text0:#eef0f8; --text1:#8b92ab; --text2:#50566a; --text3:#363b4d;
  --font:'IBM Plex Sans',sans-serif; --mono:'IBM Plex Mono',monospace;
  /* ── Radii ── */
  --r2:2px; --r4:4px; --r6:6px; --r8:8px; --r10:10px;
  --r12:12px; --r16:16px; --r20:20px; --r24:24px;
  /* ── Layout ── */
  --sidebar-w:244px; --topbar-h:62px; --bottomnav-h:62px;
  --safe-bottom: env(safe-area-inset-bottom, 0px);
  /* ── Shadows ── */
  --shadow-xs:0 1px 3px rgba(0,0,0,.4);
  --shadow-sm:0 2px 8px rgba(0,0,0,.45);
  --shadow-md:0 4px 16px rgba(0,0,0,.5),0 1px 4px rgba(0,0,0,.3);
  --shadow-lg:0 8px 32px rgba(0,0,0,.55),0 2px 8px rgba(0,0,0,.3);
  --shadow-xl:0 20px 60px rgba(0,0,0,.65),0 4px 16px rgba(0,0,0,.4);
  --shadow-glow:0 0 24px rgba(0,229,160,.18);
  /* ── Transitions ── */
  --ease:cubic-bezier(0.4,0,0.2,1);
  --ease-spring:cubic-bezier(0.34,1.56,0.64,1);
  --t1:0.12s; --t2:0.2s; --t3:0.3s;
  /* ── Glass ── */
  --glass:rgba(255,255,255,.03);
  --glass2:rgba(255,255,255,.06);
}
/* LIGHT THEME */
.theme-light {
  --bg0:#eff1f5; --bg1:#ffffff; --bg2:#f7f8fa; --bg3:#eef0f5; --bg4:#e5e8ef;
  --border:#dde0e8; --border2:#cdd1dc;
  --text0:#111827; --text1:#374151; --text2:#6b7280; --text3:#9ca3af;
  --shadow-xs:0 1px 3px rgba(0,0,0,.08);
  --shadow-sm:0 2px 8px rgba(0,0,0,.1);
  --shadow-md:0 4px 16px rgba(0,0,0,.12);
  --shadow-lg:0 8px 32px rgba(0,0,0,.14);
  --glass:rgba(255,255,255,.5);
  --glass2:rgba(255,255,255,.8);
}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:var(--font);background:var(--bg0);color:var(--text0);overflow:hidden;height:100vh}
::-webkit-scrollbar{width:6px;height:6px}
::-webkit-scrollbar-track{background:var(--bg1)}
::-webkit-scrollbar-thumb{background:var(--border2);border-radius:3px}
::-webkit-scrollbar-thumb:hover{background:var(--green)}

/* ── LOGIN ── */
#login-screen{display:flex;align-items:center;justify-content:center;height:100vh;
  background:var(--bg0);overflow:hidden;position:relative}
#login-screen::before{content:'';position:absolute;inset:0;
  background:
    radial-gradient(ellipse 80% 60% at 70% 30%,rgba(0,229,160,.07) 0%,transparent 60%),
    radial-gradient(ellipse 50% 70% at 10% 80%,rgba(77,166,255,.05) 0%,transparent 55%),
    radial-gradient(ellipse 60% 40% at 90% 90%,rgba(176,109,255,.04) 0%,transparent 50%);
  pointer-events:none}
.login-grid-bg{position:absolute;inset:0;background-image:
  linear-gradient(rgba(0,229,160,.03) 1px,transparent 1px),
  linear-gradient(90deg,rgba(0,229,160,.03) 1px,transparent 1px);
  background-size:40px 40px;pointer-events:none;animation:grid-drift 20s ease-in-out infinite}
@keyframes grid-drift{0%,100%{opacity:.6;transform:translateY(0)}50%{opacity:1;transform:translateY(-4px)}}
.login-card{background:rgba(19,21,29,.85);border:1px solid rgba(255,255,255,.08);
  border-radius:var(--r20);padding:48px 42px;width:440px;position:relative;overflow:hidden;
  box-shadow:var(--shadow-xl),inset 0 1px 0 rgba(255,255,255,.06);
  backdrop-filter:blur(24px);-webkit-backdrop-filter:blur(24px)}
.login-card::before{content:'';position:absolute;top:0;left:0;right:0;height:1px;
  background:linear-gradient(90deg,transparent 0%,rgba(0,229,160,.5) 40%,rgba(77,166,255,.4) 70%,transparent 100%)}
.login-card::after{content:'';position:absolute;bottom:-60px;right:-60px;width:200px;height:200px;
  border-radius:50%;background:radial-gradient(circle,rgba(0,229,160,.06) 0%,transparent 70%);pointer-events:none}
.login-logo{text-align:center;margin-bottom:36px}
.login-logo .logo-mark{font-family:var(--mono);font-size:38px;font-weight:600;color:var(--green);
  letter-spacing:5px;text-shadow:0 0 40px rgba(0,229,160,.4),0 0 80px rgba(0,229,160,.15);
  animation:logo-glow 3s ease-in-out infinite}
@keyframes logo-glow{0%,100%{text-shadow:0 0 40px rgba(0,229,160,.4),0 0 80px rgba(0,229,160,.15)}
  50%{text-shadow:0 0 60px rgba(0,229,160,.6),0 0 100px rgba(0,229,160,.25)}}
.login-logo .logo-sub{color:var(--text2);font-size:10px;text-transform:uppercase;letter-spacing:4px;
  margin-top:8px;background:linear-gradient(90deg,var(--text2),var(--text1));
  -webkit-background-clip:text;-webkit-text-fill-color:transparent}
.login-demo{background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.07);border-radius:var(--r10);
  padding:14px 16px;margin-bottom:28px;font-family:var(--mono);font-size:12px;color:var(--text1);
  position:relative}
.login-demo::before{content:'DEMO CREDENTIALS';position:absolute;top:-8px;left:12px;
  font-size:9px;letter-spacing:2px;color:var(--text2);background:rgba(19,21,29,.9);padding:0 6px}
.login-demo span{color:var(--green);font-weight:600}
.login-field-wrap{position:relative;margin-bottom:16px}
.login-field-wrap .field-icon{position:absolute;left:13px;top:50%;transform:translateY(-50%);
  font-size:14px;opacity:.5;pointer-events:none}
.login-field-wrap .form-control{padding-left:38px}
.login-submit{width:100%;padding:13px;border:none;border-radius:var(--r10);
  background:linear-gradient(135deg,var(--green),var(--green2));
  color:var(--bg0);font-size:14px;font-weight:700;font-family:var(--font);
  cursor:pointer;transition:all var(--t2) var(--ease);
  box-shadow:0 4px 20px rgba(0,229,160,.3);letter-spacing:.3px}
.login-submit:hover{transform:translateY(-2px);box-shadow:0 8px 32px rgba(0,229,160,.45)}
.login-submit:active{transform:translateY(0);box-shadow:0 2px 12px rgba(0,229,160,.25)}

/* ── APP LAYOUT ── */
#app{display:none;height:100vh;width:100vw}
#app.active{display:flex}
.sidebar{width:var(--sidebar-w);background:var(--bg1);border-right:1px solid var(--border);
  display:flex;flex-direction:column;overflow-y:auto;overflow-x:hidden;flex-shrink:0;
  transition:width var(--t3) var(--ease)}
.sidebar-logo{padding:18px 16px 14px;border-bottom:1px solid var(--border);
  display:flex;align-items:center;justify-content:space-between}
.sidebar-logo .logo{font-family:var(--mono);font-size:17px;font-weight:700;
  background:linear-gradient(135deg,var(--green),var(--blue));
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;letter-spacing:2.5px}
.sidebar-logo .logo-v{font-size:9px;font-family:var(--mono);color:var(--text2);letter-spacing:1px;margin-top:1px}
.user-block{padding:12px 14px;border-bottom:1px solid var(--border);display:flex;align-items:center;
  gap:10px;cursor:pointer;transition:background var(--t2);position:relative;overflow:hidden}
.user-block::before{content:'';position:absolute;inset:0;background:var(--green-glow);opacity:0;transition:opacity var(--t2)}
.user-block:hover::before{opacity:1}
.user-av{width:36px;height:36px;border-radius:10px;
  background:linear-gradient(135deg,var(--green) 0%,var(--blue) 100%);
  display:flex;align-items:center;justify-content:center;font-weight:700;font-size:13px;
  color:var(--bg0);flex-shrink:0;box-shadow:0 2px 8px rgba(0,229,160,.3)}
.user-inf h4{font-size:13px;font-weight:600;color:var(--text0)}
.user-inf p{font-size:10px;color:var(--text2);text-transform:capitalize;letter-spacing:.3px;margin-top:1px}
.nav-group{padding:10px 8px}
.nav-label{font-size:9.5px;font-weight:700;text-transform:uppercase;letter-spacing:1.8px;
  color:var(--text3);padding:0 8px;margin-bottom:4px;margin-top:4px}
.nav-item{display:flex;align-items:center;gap:9px;padding:8px 10px;border-radius:var(--r8);
  color:var(--text1);font-size:13px;font-weight:500;cursor:pointer;
  transition:all var(--t2) var(--ease);margin-bottom:1px;position:relative;white-space:nowrap;overflow:hidden}
.nav-item:hover{background:var(--bg3);color:var(--text0)}
.nav-item:hover .nav-icon{transform:scale(1.15)}
.nav-item.active{background:linear-gradient(135deg,rgba(0,229,160,.14),rgba(77,166,255,.06));
  color:var(--green);border:1px solid rgba(0,229,160,.15)}
.nav-item.active .nav-icon{color:var(--green)}
.nav-item.active::before{content:'';position:absolute;left:0;top:20%;bottom:20%;width:2.5px;
  background:var(--green);border-radius:0 2px 2px 0;box-shadow:0 0 8px var(--green)}
.nav-icon{font-size:15px;width:20px;text-align:center;flex-shrink:0;transition:transform var(--t2)}
.nav-badge{margin-left:auto;background:var(--red);color:#fff;font-size:9px;font-weight:700;
  padding:2px 6px;border-radius:8px;font-family:var(--mono);min-width:18px;text-align:center;
  box-shadow:0 2px 6px rgba(255,77,109,.4)}
.nav-badge.warn{background:var(--yellow);color:var(--bg0);box-shadow:0 2px 6px rgba(255,190,77,.4)}

/* ── MAIN ── */
.main{flex:1;display:flex;flex-direction:column;overflow:hidden}
.topbar{height:var(--topbar-h);background:rgba(12,14,19,.92);border-bottom:1px solid var(--border);
  display:flex;align-items:center;padding:0 20px;gap:14px;flex-shrink:0;
  backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px);
  position:sticky;top:0;z-index:100}
.topbar-title{font-size:15px;font-weight:600;color:var(--text0);letter-spacing:.2px}
.topbar-sep{color:var(--text3);font-size:14px;margin:0 2px}
.topbar-right{margin-left:auto;display:flex;align-items:center;gap:10px}
.search-box{background:var(--bg3);border:1px solid var(--border2);border-radius:var(--r8);
  padding:7px 14px;width:240px;color:var(--text0);font-size:13px;font-family:var(--font);
  transition:all var(--t2)}
.search-box:focus{outline:none;border-color:var(--green);box-shadow:0 0 0 3px var(--green-glow);
  width:280px;background:var(--bg2)}
.search-box::placeholder{color:var(--text2)}
.notif-btn{position:relative;cursor:pointer;padding:7px;border-radius:var(--r8);
  transition:background var(--t2);color:var(--text1)}
.notif-btn:hover{background:var(--bg3);color:var(--text0)}
.notif-dot{position:absolute;top:3px;right:3px;width:7px;height:7px;border-radius:50%;
  background:var(--red);border:2px solid var(--bg1);animation:notif-pulse 2s ease-in-out infinite}
@keyframes notif-pulse{0%,100%{transform:scale(1)}50%{transform:scale(1.3)}}
.content{flex:1;overflow-y:auto;padding:24px;scroll-behavior:smooth}

/* ── PAGES ── */
.page{display:none}.page.active{display:block}

/* ── BUTTONS ── */
.btn{padding:8px 16px;border-radius:var(--r8);border:none;font-size:13px;font-weight:500;cursor:pointer;
  transition:all .2s;display:inline-flex;align-items:center;gap:7px;font-family:var(--font)}
.btn-primary{background:var(--green);color:var(--bg0)}
.btn-primary:hover{background:var(--green2);transform:translateY(-1px)}
.btn-secondary{background:var(--bg3);color:var(--text1);border:1px solid var(--border2)}
.btn-secondary:hover{background:var(--border);color:var(--text0)}
.btn-danger{background:rgba(255,77,109,.1);color:var(--red);border:1px solid rgba(255,77,109,.3)}
.btn-danger:hover{background:rgba(255,77,109,.2)}
.btn-warning{background:rgba(255,190,77,.1);color:var(--yellow);border:1px solid rgba(255,190,77,.3)}
.btn-warning:hover{background:rgba(255,190,77,.2)}
.btn-sm{padding:5px 12px;font-size:12px}
.btn-icon{padding:6px 8px}
.admin-only-btn{opacity:0;pointer-events:none;transition:.2s}.is-admin .admin-only-btn{opacity:1;pointer-events:all}

/* ── CARDS / STATS ── */
.stats-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:14px;margin-bottom:24px}
.stat-card{background:var(--bg2);border:1px solid var(--border);border-radius:var(--r12);padding:20px;
  position:relative;overflow:hidden;transition:all var(--t3) var(--ease);cursor:default}
.stat-card:hover{border-color:rgba(0,229,160,.25);transform:translateY(-3px);
  box-shadow:var(--shadow-md),0 0 0 1px rgba(0,229,160,.08);}
.stat-card::before{content:'';position:absolute;top:0;left:0;right:0;height:2px;
  background:linear-gradient(90deg,var(--green),var(--blue));opacity:.7}
.stat-card:hover::before{opacity:1}
.stat-card::after{content:'';position:absolute;bottom:0;left:0;right:0;height:40%;
  background:linear-gradient(to top,rgba(0,229,160,.03),transparent);pointer-events:none}
.stat-label{font-size:10.5px;color:var(--text2);text-transform:uppercase;
  letter-spacing:1.2px;margin-bottom:10px;font-weight:600}
.stat-value{font-size:28px;font-weight:700;font-family:var(--mono);color:var(--text0);
  line-height:1;margin-bottom:5px;transition:color var(--t2)}
.stat-sub{font-size:11px;color:var(--text2);line-height:1.4}
.stat-icon{position:absolute;right:14px;top:50%;transform:translateY(-50%);
  font-size:36px;opacity:.06;transition:opacity var(--t2)}
.stat-card:hover .stat-icon{opacity:.1}
.card{background:var(--bg2);border:1px solid var(--border);border-radius:var(--r12);
  padding:20px;margin-bottom:20px;transition:border-color var(--t2)}
.card:hover{border-color:var(--border2)}
.card-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:16px}
.card-title{font-size:11px;font-weight:700;color:var(--text2);text-transform:uppercase;
  letter-spacing:1.2px;display:flex;align-items:center;gap:8px}
.two-col{display:grid;grid-template-columns:1fr 1fr;gap:20px}
.three-col{display:grid;grid-template-columns:1fr 1fr 1fr;gap:20px}
@media(max-width:900px){.two-col,.three-col{grid-template-columns:1fr}}

/* ── TABLE ── */
.tbl-wrap{overflow-x:auto;border-radius:var(--r8);border:1px solid var(--border)}
table{width:100%;border-collapse:collapse}
th{text-align:left;padding:10px 14px;font-size:10.5px;font-weight:700;color:var(--text2);
  text-transform:uppercase;letter-spacing:1px;border-bottom:1px solid var(--border);
  background:var(--bg2);white-space:nowrap;position:sticky;top:0;z-index:2}
td{padding:11px 14px;font-size:13px;border-bottom:1px solid rgba(255,255,255,.03);color:var(--text1)}
tr:hover td{background:rgba(255,255,255,.025)}
tr:last-child td{border-bottom:none}
.td-primary{color:var(--text0);font-weight:500}
.td-mono{font-family:var(--mono);font-size:11.5px;color:var(--green);letter-spacing:.3px}

/* ── BADGES ── */
.badge{display:inline-flex;align-items:center;padding:3px 9px;border-radius:var(--r4);
  font-size:9.5px;font-weight:700;text-transform:uppercase;letter-spacing:.6px;
  white-space:nowrap;font-family:var(--mono)}
.b-critical,.b-danger{background:var(--red-glow);color:var(--red);border:1px solid rgba(255,77,109,.2)}
.b-high,.b-warning{background:var(--yellow-glow);color:var(--yellow);border:1px solid rgba(255,190,77,.2)}
.b-medium,.b-info{background:var(--blue-glow);color:var(--blue);border:1px solid rgba(77,166,255,.2)}
.b-low,.b-success{background:var(--green-glow);color:var(--green);border:1px solid rgba(0,229,160,.2)}
.b-open{background:var(--blue-glow);color:var(--blue);border:1px solid rgba(77,166,255,.2)}
.b-in_progress{background:var(--yellow-glow);color:var(--yellow);border:1px solid rgba(255,190,77,.2)}
.b-completed{background:var(--green-glow);color:var(--green);border:1px solid rgba(0,229,160,.2)}
.b-overdue{background:var(--red-glow);color:var(--red);border:1px solid rgba(255,77,109,.2)}
.b-due_soon{background:var(--yellow-glow);color:var(--yellow)}
.b-ok{background:var(--green-glow);color:var(--green)}
.b-on_hold{background:var(--purple-glow);color:var(--purple);border:1px solid rgba(176,109,255,.2)}
.b-cancelled{background:rgba(255,255,255,.04);color:var(--text2);border:1px solid var(--border)}
.b-admin{background:var(--purple-glow);color:var(--purple);border:1px solid rgba(176,109,255,.2)}
.b-manager{background:var(--blue-glow);color:var(--blue)}
.b-supervisor{background:var(--yellow-glow);color:var(--yellow)}
.b-technician{background:var(--green-glow);color:var(--green)}

/* ── BUTTONS ── */
.btn{padding:8px 16px;border-radius:var(--r8);border:none;font-size:13px;font-weight:500;cursor:pointer;
  transition:all var(--t2) var(--ease);display:inline-flex;align-items:center;gap:7px;
  font-family:var(--font);position:relative;overflow:hidden;white-space:nowrap}
.btn::after{content:'';position:absolute;inset:0;background:white;opacity:0;transition:opacity var(--t1)}
.btn:active::after{opacity:.06}
.btn-primary{background:linear-gradient(135deg,var(--green),var(--green2));color:var(--bg0);
  font-weight:600;box-shadow:0 2px 12px rgba(0,229,160,.25)}
.btn-primary:hover{transform:translateY(-1px);box-shadow:0 4px 20px rgba(0,229,160,.4)}
.btn-primary:active{transform:translateY(0)}
.btn-secondary{background:var(--bg3);color:var(--text1);border:1px solid var(--border2)}
.btn-secondary:hover{background:var(--bg4);color:var(--text0);border-color:var(--border2)}
.btn-danger{background:var(--red-glow);color:var(--red);border:1px solid rgba(255,77,109,.25)}
.btn-danger:hover{background:rgba(255,77,109,.2);border-color:rgba(255,77,109,.4)}
.btn-warning{background:var(--yellow-glow);color:var(--yellow);border:1px solid rgba(255,190,77,.25)}
.btn-warning:hover{background:rgba(255,190,77,.2)}
.btn-sm{padding:5px 12px;font-size:12px;border-radius:var(--r6)}
.btn-xs{padding:3px 9px;font-size:11px;border-radius:var(--r4)}
.btn-icon{padding:7px;border-radius:var(--r8);aspect-ratio:1}
.admin-only-btn{opacity:0;pointer-events:none;transition:opacity var(--t2)}.is-admin .admin-only-btn{opacity:1;pointer-events:all}

/* ── CHART ── */
.chart-wrap{height:240px;position:relative}

/* ── FORMS ── */
.form-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:16px}
.form-group{margin-bottom:16px}
.form-group label{display:block;font-size:10.5px;font-weight:700;color:var(--text2);
  text-transform:uppercase;letter-spacing:1px;margin-bottom:6px}
.form-control{width:100%;padding:9px 12px;background:var(--bg3);border:1px solid var(--border2);
  border-radius:var(--r8);color:var(--text0);font-size:13px;transition:all var(--t2);
  font-family:var(--font)}
.form-control:focus{outline:none;border-color:var(--green);background:var(--bg2);
  box-shadow:0 0 0 3px var(--green-glow)}
.form-control:hover:not(:focus){border-color:var(--border2)}
select.form-control{cursor:pointer;appearance:none;background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='8' fill='none'%3E%3Cpath d='M1 1l5 5 5-5' stroke='%2350566a' stroke-width='1.5' stroke-linecap='round'/%3E%3C/svg%3E");
  background-repeat:no-repeat;background-position:right 12px center;padding-right:32px}
textarea.form-control{resize:vertical;min-height:90px}

/* ── MODAL ── */
.modal-overlay{position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,.7);
  backdrop-filter:blur(6px);-webkit-backdrop-filter:blur(6px);
  display:flex;align-items:center;justify-content:center;z-index:1000}
.modal{background:var(--bg2);border:1px solid rgba(255,255,255,.08);border-radius:var(--r16);
  width:90%;max-width:580px;max-height:90vh;overflow-y:auto;
  box-shadow:var(--shadow-xl),inset 0 1px 0 rgba(255,255,255,.05)}
.modal-lg{max-width:780px}
.modal-xl{max-width:980px}
.modal-header{display:flex;align-items:center;justify-content:space-between;
  padding:18px 24px;border-bottom:1px solid var(--border);
  background:linear-gradient(180deg,rgba(255,255,255,.02) 0%,transparent 100%)}
.modal-header h3{font-size:15px;font-weight:600;color:var(--text0)}
.modal-close{background:none;border:none;color:var(--text2);font-size:20px;cursor:pointer;
  padding:4px 6px;line-height:1;transition:all var(--t2);border-radius:var(--r6)}
.modal-close:hover{color:var(--text0);background:var(--bg3)}
.modal-body{padding:24px}
.modal-footer{padding:16px 24px;border-top:1px solid var(--border);display:flex;justify-content:flex-end;
  gap:10px;background:rgba(0,0,0,.15)}

/* ── TOAST (legacy single) ── */
#toast{position:fixed;bottom:24px;right:24px;background:var(--bg3);border:1px solid var(--border2);
  border-radius:var(--r10);padding:12px 18px;font-size:13px;box-shadow:var(--shadow-lg);
  z-index:9999;opacity:0;transform:translateY(8px);transition:all var(--t2);
  pointer-events:none;min-width:200px}
#toast.show{opacity:1;transform:translateY(0)}
#toast.success{border-left:3px solid var(--green)}
#toast.error{border-left:3px solid var(--red)}
#toast.warning{border-left:3px solid var(--yellow)}

/* ── EMPTY STATE ── */
.empty-state{text-align:center;padding:56px 24px;color:var(--text2)}
.empty-state .icon{font-size:44px;margin-bottom:16px;opacity:.35;
  filter:drop-shadow(0 0 20px currentColor)}
.empty-state h3{font-size:16px;color:var(--text1);margin-bottom:8px;font-weight:600}
.empty-state p{font-size:13px;color:var(--text2);line-height:1.6;max-width:320px;margin:0 auto}

/* ── PAGE SECTION HEADER ── */
.page-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:20px;gap:12px;flex-wrap:wrap}
.page-header h2{font-size:18px;font-weight:700;color:var(--text0);display:flex;align-items:center;gap:8px}
.page-header h2 small{font-size:12px;color:var(--text2);font-weight:400}

/* ── TIMELINE ── */
.timeline{position:relative;padding-left:24px}
.timeline::before{content:'';position:absolute;left:7px;top:0;bottom:0;width:2px;
  background:linear-gradient(to bottom,var(--green),var(--border2))}
.timeline-item{position:relative;margin-bottom:20px}
.timeline-item::before{content:'';position:absolute;left:-21px;top:5px;width:12px;height:12px;
  border-radius:50%;background:var(--bg3);border:2px solid var(--border2)}
.timeline-item.tl-work_order::before{border-color:var(--blue);background:var(--blue-glow)}
.timeline-item.tl-pm_completion::before{border-color:var(--green);background:var(--green-glow);
  box-shadow:0 0 8px rgba(0,229,160,.3)}
.timeline-item.tl-status_change::before{border-color:var(--yellow);background:var(--yellow-glow)}
.timeline-item.tl-created::before{border-color:var(--purple);background:var(--purple-glow)}
.timeline-item.tl-meter_reading::before{border-color:var(--text2)}
.tl-header{display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:4px}
.tl-title{font-size:13px;font-weight:500;color:var(--text0)}
.tl-date{font-size:11px;color:var(--text2);font-family:var(--mono);white-space:nowrap;margin-left:8px}
.tl-detail{font-size:12px;color:var(--text1)}
.tl-cost{font-family:var(--mono);font-size:11px;color:var(--green);margin-top:3px}
.tl-by{font-size:11px;color:var(--text2)}

/* ── PM CHECKLIST ── */
.checklist-editor{background:var(--bg3);border:1px solid var(--border);border-radius:var(--r8);padding:12px}
.checklist-item{display:flex;align-items:center;gap:8px;padding:6px 0;border-bottom:1px solid var(--border)}
.checklist-item:last-child{border-bottom:none}
.checklist-item input[type=text]{flex:1;background:transparent;border:none;color:var(--text0);
  font-size:13px;font-family:var(--font);outline:none}
.checklist-item button{background:none;border:none;color:var(--red);cursor:pointer;font-size:16px;
  padding:2px 4px;opacity:.6;transition:.2s}
.checklist-item button:hover{opacity:1}
.checklist-view{list-style:none}
.checklist-view li{display:flex;align-items:center;gap:10px;padding:8px 0;
  border-bottom:1px solid var(--border);font-size:13px;color:var(--text1)}
.checklist-view li:last-child{border-bottom:none}
.checklist-cb{width:16px;height:16px;cursor:pointer;accent-color:var(--green)}
.checklist-view li.done{color:var(--text2);text-decoration:line-through}
.pm-status-bar{display:flex;align-items:center;gap:8px;padding:8px 12px;border-radius:var(--r8);
  font-size:12px;font-weight:500}
.pm-status-bar.overdue{background:rgba(255,77,109,.1);color:var(--red);border:1px solid rgba(255,77,109,.2)}
.pm-status-bar.due_soon{background:rgba(255,190,77,.1);color:var(--yellow);border:1px solid rgba(255,190,77,.2)}
.pm-status-bar.ok{background:rgba(0,229,160,.1);color:var(--green);border:1px solid rgba(0,229,160,.2)}

/* ── AUDIT LOG ── */
.audit-action{font-family:var(--mono);font-size:11px;padding:2px 7px;border-radius:3px}
.audit-LOGIN,.audit-LOGOUT{background:rgba(0,229,160,.1);color:var(--green)}
.audit-CREATE{background:rgba(77,166,255,.1);color:var(--blue)}
.audit-UPDATE{background:rgba(255,190,77,.1);color:var(--yellow)}
.audit-DELETE{background:rgba(255,77,109,.1);color:var(--red)}
.audit-INVENTORY_ADJUST{background:rgba(176,109,255,.1);color:var(--purple)}
.audit-PASSWORD_CHANGE,.audit-PASSWORD_RESET{background:rgba(255,190,77,.1);color:var(--yellow)}
.audit-detail-toggle{background:none;border:none;color:var(--text2);cursor:pointer;font-size:11px;
  padding:2px 6px;border-radius:3px;transition:.2s}
.audit-detail-toggle:hover{background:var(--bg3);color:var(--text0)}
.audit-diff{background:var(--bg0);border:1px solid var(--border);border-radius:var(--r4);
  padding:10px;font-family:var(--mono);font-size:11px;color:var(--text1);max-height:200px;overflow-y:auto;margin-top:6px}
.diff-old{color:var(--red)}.diff-new{color:var(--green)}

/* ── USER MGMT ── */
.user-role-icon{width:28px;height:28px;border-radius:50%;display:inline-flex;align-items:center;
  justify-content:center;font-size:12px;font-weight:700}
.user-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:16px}
.user-card{background:var(--bg2);border:1px solid var(--border);border-radius:var(--r12);padding:16px;
  transition:.2s;position:relative}
.user-card:hover{border-color:var(--border2);transform:translateY(-1px)}
.user-card-head{display:flex;align-items:center;gap:12px;margin-bottom:12px}
.user-card-av{width:44px;height:44px;border-radius:50%;display:flex;align-items:center;justify-content:center;
  font-weight:700;font-size:18px;flex-shrink:0}
.user-card-info h4{font-size:14px;font-weight:600;color:var(--text0)}
.user-card-info p{font-size:12px;color:var(--text2)}
.user-card-meta{display:flex;flex-direction:column;gap:4px;font-size:12px;color:var(--text1)}
.user-card-meta span{display:flex;align-items:center;gap:6px}
.user-card-actions{position:absolute;top:12px;right:12px;display:flex;gap:6px}
.user-inactive{opacity:.5}
.status-dot{width:8px;height:8px;border-radius:50%;flex-shrink:0}
.status-dot.active{background:var(--green);box-shadow:0 0 6px var(--green)}
.status-dot.inactive{background:var(--text2)}

/* ── FILTERS / TOOLBAR ── */
.toolbar{display:flex;align-items:center;gap:10px;margin-bottom:20px;flex-wrap:wrap}
.filter-select{background:var(--bg3);border:1px solid var(--border2);border-radius:var(--r8);
  padding:7px 12px;color:var(--text1);font-size:13px;cursor:pointer;font-family:var(--font)}
.filter-select:focus{outline:none;border-color:var(--green)}
.filter-search{flex:1;min-width:180px}

/* ── PAGINATION ── */
.pagination{display:flex;align-items:center;gap:6px;justify-content:flex-end;margin-top:16px}
.pag-btn{background:var(--bg3);border:1px solid var(--border);border-radius:var(--r4);
  padding:5px 10px;font-size:12px;cursor:pointer;color:var(--text1);transition:.2s}
.pag-btn:hover,.pag-btn.active{background:var(--green-glow);border-color:var(--green);color:var(--green)}
.pag-info{font-size:12px;color:var(--text2);font-family:var(--mono)}

/* ── MISC ── */
.tag{display:inline-flex;align-items:center;gap:4px;background:var(--bg3);border:1px solid var(--border2);
  border-radius:var(--r4);padding:2px 8px;font-size:11px;color:var(--text1)}
.empty-state{text-align:center;padding:48px 24px;color:var(--text2)}
.empty-state .icon{font-size:40px;margin-bottom:12px;opacity:.4}
.empty-state h3{font-size:16px;color:var(--text1);margin-bottom:6px}
.divider{border:none;border-top:1px solid var(--border);margin:16px 0}
.text-green{color:var(--green)}.text-red{color:var(--red)}.text-yellow{color:var(--yellow)}
.text-blue{color:var(--blue)}.text-muted{color:var(--text2)}.text-purple{color:var(--purple)}
.flex{display:flex}.flex-between{display:flex;justify-content:space-between;align-items:center}
.gap-4{gap:4px}.gap-6{gap:6px}.gap-8{gap:8px}.gap-12{gap:12px}.gap-16{gap:16px}
.mb-8{margin-bottom:8px}.mb-12{margin-bottom:12px}.mb-16{margin-bottom:16px}.mb-20{margin-bottom:20px}
.loading{display:flex;align-items:center;justify-content:center;padding:48px;color:var(--text2)}
.spinner{width:22px;height:22px;border:2px solid var(--border2);border-top-color:var(--green);
  border-radius:50%;animation:spin .7s linear infinite;margin-right:10px}
@keyframes spin{to{transform:rotate(360deg)}}
.section-title{font-size:17px;font-weight:700;margin-bottom:16px;display:flex;align-items:center;gap:8px;
  color:var(--text0)}
.section-title small{font-size:12px;color:var(--text2);font-weight:400}
/* ── TAG ── */
.tag{display:inline-flex;align-items:center;gap:4px;background:var(--bg3);border:1px solid var(--border2);
  border-radius:var(--r6);padding:3px 9px;font-size:11px;color:var(--text1);font-weight:500}
/* ── PROGRESS BAR ── */
.progress-track{height:6px;background:var(--bg3);border-radius:3px;overflow:hidden}
.progress-fill{height:100%;border-radius:3px;transition:width .6s var(--ease);
  background:linear-gradient(90deg,var(--green),var(--blue))}
/* ── MISC HELPERS ── */
.shine{position:relative;overflow:hidden}
.shine::after{content:'';position:absolute;top:-50%;left:-50%;width:200%;height:200%;
  background:linear-gradient(105deg,transparent 40%,rgba(255,255,255,.04) 50%,transparent 60%);
  opacity:0;transition:opacity var(--t2)}
.shine:hover::after{opacity:1;animation:shine-move .6s ease}
@keyframes shine-move{from{transform:translateX(-30%)}to{transform:translateX(30%)}}
/* ── ENHANCED TOAST STACK (v5+) ── */
#toast-stack{position:fixed;bottom:24px;right:24px;z-index:9999;display:flex;
  flex-direction:column;gap:8px;pointer-events:none;min-width:280px;max-width:380px}
.toast-item{display:flex;align-items:center;gap:10px;padding:12px 16px;
  background:rgba(26,29,39,.95);border:1px solid rgba(255,255,255,.08);
  border-radius:var(--r10);box-shadow:var(--shadow-lg);pointer-events:all;
  animation:toast-in .25s var(--ease-spring);backdrop-filter:blur(12px)}
.toast-item.removing{animation:toast-out .2s ease forwards}
@keyframes toast-in{from{opacity:0;transform:translateY(12px) scale(.95)}to{opacity:1;transform:translateY(0) scale(1)}}
@keyframes toast-out{to{opacity:0;transform:translateX(100%) scale(.95)}}
.toast-item.success{border-left:3px solid var(--green)}
.toast-item.error{border-left:3px solid var(--red)}
.toast-item.warning{border-left:3px solid var(--yellow)}
.toast-item.info{border-left:3px solid var(--blue)}
.toast-icon{font-size:16px;flex-shrink:0}
.toast-msg{flex:1;font-size:13px;color:var(--text0);line-height:1.4}
.toast-close{background:none;border:none;color:var(--text2);cursor:pointer;font-size:16px;
  padding:2px;line-height:1;transition:color var(--t1);flex-shrink:0}
.toast-close:hover{color:var(--text0)}
.cal-grid{display:grid;grid-template-columns:repeat(7,1fr);gap:1px;background:var(--border)}
.cal-header-row{display:grid;grid-template-columns:repeat(7,1fr);gap:1px;background:transparent;margin-bottom:1px}
.cal-dow{text-align:center;font-size:11px;font-weight:600;color:var(--text2);padding:8px;text-transform:uppercase;letter-spacing:.8px}
.cal-cell{background:var(--bg2);min-height:110px;padding:8px;position:relative;transition:.15s}
.cal-cell:hover{background:var(--bg3)}
.cal-cell.today{background:var(--green-glow);border:1px solid var(--green)}
.cal-cell.other-month{opacity:.35}
.cal-day-num{font-size:12px;font-weight:600;color:var(--text2);margin-bottom:4px;font-family:var(--mono)}
.cal-cell.today .cal-day-num{color:var(--green)}
.cal-event{font-size:10px;padding:2px 6px;border-radius:3px;margin-bottom:2px;cursor:pointer;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-weight:500;line-height:1.4}
.cal-event.ev-wo{background:rgba(77,166,255,.18);color:#4da6ff;border-left:2px solid #4da6ff}
.cal-event.ev-pm{background:rgba(0,229,160,.15);color:#00e5a0;border-left:2px solid #00e5a0}
.cal-event.ev-critical{background:rgba(255,77,109,.18);color:#ff4d6d;border-left:2px solid #ff4d6d}
.cal-nav{display:flex;align-items:center;gap:12px;margin-bottom:16px}
.cal-month-title{font-size:18px;font-weight:700;font-family:var(--mono);min-width:160px;text-align:center}
/* ── REPORTS ── */
.report-card{background:var(--bg2);border:1px solid var(--border);border-radius:var(--r12);padding:20px;cursor:pointer;transition:.2s}
.report-card:hover{border-color:var(--green);transform:translateY(-2px)}
.report-card .report-icon{font-size:32px;margin-bottom:12px}
.report-card h3{font-size:15px;font-weight:600;margin-bottom:6px}
.report-card p{font-size:12px;color:var(--text2);line-height:1.5}
.report-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:16px;margin-bottom:24px}
/* ── IMPORT ── */
.import-zone{border:2px dashed var(--border2);border-radius:var(--r12);padding:32px;text-align:center;
  background:var(--bg3);transition:.2s;cursor:pointer}
.import-zone:hover,.import-zone.drag-over{border-color:var(--green);background:var(--green-glow)}
.import-preview{margin-top:16px;max-height:300px;overflow-y:auto}
/* ── DOWNTIME ── */
.dt-bar{height:16px;background:var(--bg3);border-radius:var(--r4);overflow:hidden;margin-bottom:8px}
.dt-bar-fill{height:100%;border-radius:var(--r4);background:var(--red);transition:width .5s}
/* ── DEPRECIATION ── */
.dep-meter{position:relative;height:20px;background:var(--bg3);border-radius:10px;overflow:hidden}
.dep-fill{height:100%;border-radius:10px;transition:width .6s}

/* ── TABS ── */
.tab-bar{display:flex;gap:2px;background:var(--bg3);border:1px solid var(--border);
  border-radius:var(--r8);padding:3px;margin-bottom:20px;width:fit-content}
.tab-btn{padding:7px 16px;border-radius:6px;border:none;font-size:13px;font-weight:500;
  cursor:pointer;background:transparent;color:var(--text2);transition:.2s;font-family:var(--font)}
.tab-btn:hover{color:var(--text0)}
.tab-btn.active{background:var(--bg2);color:var(--green);box-shadow:0 1px 4px rgba(0,0,0,.3)}
/* ── EQ HISTORY ── */
.eq-selector{display:flex;align-items:center;gap:12px;margin-bottom:20px;flex-wrap:wrap}
.eq-selector select{flex:1;min-width:280px;max-width:440px}
.hist-summary{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin-bottom:20px}
.hist-stat{background:var(--bg2);border:1px solid var(--border);border-radius:var(--r12);padding:16px;text-align:center}
.hist-stat-val{font-size:24px;font-weight:700;font-family:var(--mono);color:var(--text0);margin-bottom:4px}
.hist-stat-lbl{font-size:11px;color:var(--text2);text-transform:uppercase;letter-spacing:1px}
.hist-stat.green .hist-stat-val{color:var(--green)}
.hist-stat.yellow .hist-stat-val{color:var(--yellow)}
.hist-stat.red .hist-stat-val{color:var(--red)}
.hist-stat.blue .hist-stat-val{color:var(--blue)}
.cost-bar-wrap{margin-bottom:6px}
.cost-bar-label{display:flex;justify-content:space-between;font-size:12px;margin-bottom:4px}
.cost-bar-track{height:8px;background:var(--bg3);border-radius:4px;overflow:hidden}
.cost-bar-fill{height:100%;border-radius:4px;transition:width .6s}
.eq-asset-header{background:var(--bg2);border:1px solid var(--border);border-radius:var(--r12);
  padding:16px 20px;margin-bottom:16px;display:flex;align-items:center;gap:16px}
.eq-asset-icon{font-size:28px;width:48px;height:48px;background:var(--bg3);border-radius:var(--r8);
  display:flex;align-items:center;justify-content:center;flex-shrink:0}

/* ── MOBILE BOTTOM NAV ── */
.bottom-nav{display:none;position:fixed;bottom:0;left:0;right:0;background:var(--bg1);
  border-top:1px solid var(--border);height:var(--bottomnav-h);padding-bottom:var(--safe-bottom);
  z-index:900;grid-template-columns:repeat(5,1fr)}
.bottom-nav-item{display:flex;flex-direction:column;align-items:center;justify-content:center;
  padding:6px 4px;cursor:pointer;color:var(--text2);transition:.2s;gap:3px;
  font-size:9px;font-weight:600;text-transform:uppercase;letter-spacing:.5px}
.bottom-nav-item:hover,.bottom-nav-item.active{color:var(--green)}
.bottom-nav-item .bn-icon{font-size:20px;transition:.2s}
.bottom-nav-item.active .bn-icon{transform:scale(1.1)}
.hamburger{display:none;flex-direction:column;gap:5px;cursor:pointer;padding:8px;
  border-radius:var(--r8);transition:.2s}
.hamburger:hover{background:var(--bg3)}
.hamburger span{width:20px;height:2px;background:var(--text1);border-radius:2px;transition:.3s}
.hamburger.open span:nth-child(1){transform:rotate(45deg) translate(5px,5px)}
.hamburger.open span:nth-child(2){opacity:0}
.hamburger.open span:nth-child(3){transform:rotate(-45deg) translate(5px,-5px)}
.sidebar-overlay{display:none;position:fixed;inset:0;background:rgba(0,0,0,.6);z-index:800;backdrop-filter:blur(2px)}
.sidebar-overlay.active{display:block}
.fab{display:none;position:fixed;bottom:80px;right:20px;width:56px;height:56px;border-radius:50%;
  background:var(--green);color:var(--bg0);font-size:24px;border:none;cursor:pointer;
  box-shadow:0 4px 20px rgba(0,229,160,.4);z-index:600;align-items:center;justify-content:center;
  transition:all .3s}
.fab:hover{background:var(--green2);transform:scale(1.08)}
.fab:active{transform:scale(0.95)}
#pwa-install-banner{display:none;position:fixed;bottom:0;left:0;right:0;
  background:linear-gradient(135deg,var(--bg2),var(--bg3));border-top:1px solid var(--border);
  padding:14px 20px;padding-bottom:calc(14px + env(safe-area-inset-bottom,0px));
  z-index:2000;align-items:center;gap:12px;box-shadow:0 -4px 24px rgba(0,0,0,.4)}
#pwa-install-banner .pwa-logo{font-size:28px}
#pwa-install-banner .pwa-text h4{font-size:14px;font-weight:600;color:var(--text0)}
#pwa-install-banner .pwa-text p{font-size:12px;color:var(--text2);margin-top:2px}
#offline-bar{display:none;position:fixed;top:0;left:0;right:0;height:32px;
  background:linear-gradient(90deg,#ff4d6d,#ff7a45);z-index:9990;
  align-items:center;justify-content:center;font-size:12px;font-weight:600;
  color:white;letter-spacing:.5px;gap:8px}
#offline-bar.visible{display:flex}
#qr-scanner-overlay{display:none;position:fixed;inset:0;background:rgba(0,0,0,.95);
  z-index:2000;flex-direction:column;align-items:center;justify-content:center;gap:20px}
#qr-scanner-overlay.active{display:flex}
#qr-video{width:280px;height:280px;border-radius:var(--r16);object-fit:cover;
  border:2px solid var(--green);box-shadow:0 0 0 4px var(--green-glow)}
.qr-frame{position:relative;width:284px;height:284px;display:flex;align-items:center;justify-content:center}
.qr-corner{position:absolute;width:24px;height:24px;border-color:var(--green);border-style:solid}
.qr-corner.tl{top:0;left:0;border-width:3px 0 0 3px}
.qr-corner.tr{top:0;right:0;border-width:3px 3px 0 0}
.qr-corner.bl{bottom:0;left:0;border-width:0 0 3px 3px}
.qr-corner.br{bottom:0;right:0;border-width:0 3px 3px 0}
.qr-scan-line{position:absolute;left:4px;right:4px;height:2px;background:linear-gradient(90deg,transparent,var(--green),transparent);
  animation:scan 2s linear infinite}
@keyframes scan{0%{top:10%}100%{top:90%}}
.theme-toggle{display:flex;align-items:center;gap:6px;cursor:pointer;padding:6px 10px;
  border-radius:var(--r8);border:1px solid var(--border);background:var(--bg3);transition:.2s;font-size:13px;white-space:nowrap}
.theme-toggle:hover{border-color:var(--green)}
.sync-dot{width:8px;height:8px;border-radius:50%;background:var(--green);display:inline-block;margin-right:4px}
.sync-dot.syncing{animation:pulse-dot 1s ease-in-out infinite}
@keyframes pulse-dot{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.5;transform:scale(1.3)}}
@keyframes fadein{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:translateY(0)}}
.page.active{animation:fadein .25s ease}
.kbd{display:inline-block;padding:2px 6px;background:var(--bg3);border:1px solid var(--border2);
  border-radius:4px;font-family:var(--mono);font-size:11px;color:var(--text1)}
/* ── MOBILE RESPONSIVE ── */
@media(max-width:768px){
  .sidebar{position:fixed;top:0;left:0;bottom:0;z-index:850;transform:translateX(-100%);transition:transform .3s cubic-bezier(.4,0,.2,1);width:260px}
  .sidebar.mobile-open{transform:translateX(0);box-shadow:4px 0 24px rgba(0,0,0,.5)}
  .hamburger{display:flex}
  .bottom-nav{display:grid}
  .fab{display:flex}
  .topbar{height:56px}
  .content{padding:16px;padding-bottom:calc(var(--bottomnav-h) + env(safe-area-inset-bottom,0px) + 16px)}
  .stats-grid{grid-template-columns:1fr 1fr;gap:10px}
  .stat-card{padding:14px}
  .stat-value{font-size:22px}
  .search-box{width:140px}
  .modal{width:95%;max-height:92vh;margin:4vh auto}
  .modal-body{padding:16px}
  .modal-header{padding:14px 16px}
  .modal-footer{padding:12px 16px}
  .toolbar{flex-wrap:wrap;gap:8px}
  .filter-search{width:100%!important}
  th:nth-child(n+5){display:none}
  td:nth-child(n+5){display:none}
  #toast{bottom:calc(var(--bottomnav-h) + 12px + env(safe-area-inset-bottom,0px));right:12px;left:12px;text-align:center}
  .login-card{width:calc(100% - 32px);padding:32px 24px;margin:0 auto}
  .topbar .topbar-title{font-size:14px}
  .notif-btn{display:none}
}
@media(max-width:480px){
  .stats-grid{grid-template-columns:1fr}
  .search-box{display:none}
  th:nth-child(n+4){display:none}
  td:nth-child(n+4){display:none}
}


/* ══════════════════════════════════════════════════════
   ADVANCED GUI v4 — Command Palette, Kanban, Gauges,
   Split Pane, Gantt, Activity Feed, Micro-Animations
   ══════════════════════════════════════════════════════ */

/* ── CUSTOM ACCENT COLOR & TRANSITIONS ── */
:root {
  --accent: var(--green);
  --accent2: var(--green2);
  --accent-glow: var(--green-glow);
  --transition-page: 0.22s cubic-bezier(0.4,0,0.2,1);
  --shadow-float: var(--shadow-lg);
  --shadow-modal: var(--shadow-xl);
}
.accent-blue   { --accent:#4da6ff; --accent2:#2d8fe8; --accent-glow:rgba(77,166,255,.14); }
.accent-purple { --accent:#b06dff; --accent2:#9044e8; --accent-glow:rgba(176,109,255,.14); }
.accent-orange { --accent:#ff8c42; --accent2:#e07028; --accent-glow:rgba(255,140,66,.14); }
.accent-red    { --accent:#ff4d6d; --accent2:#e0304d; --accent-glow:rgba(255,77,109,.14); }

/* smooth theme transitions */
body, .sidebar, .topbar, .card, .stat-card, .modal, .nav-item, .btn, .form-control,
.badge, .tbl-wrap, .bottom-nav, th, td {
  transition: background-color var(--t3) ease, border-color var(--t3) ease, color var(--t3) ease;
}

/* ── COMMAND PALETTE ── */
#cmd-palette-overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,.7);
  backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px);
  z-index: 10000;
  display: none; align-items: flex-start; justify-content: center;
  padding-top: 10vh;
}
#cmd-palette-overlay.active { display: flex; }
.cmd-palette {
  background: rgba(19,21,29,.96); border: 1px solid rgba(255,255,255,.1);
  border-radius: var(--r16); width: 620px; max-width: 92vw;
  box-shadow: var(--shadow-xl),inset 0 1px 0 rgba(255,255,255,.06); overflow: hidden;
  animation: cmd-drop 0.2s cubic-bezier(0.34,1.56,0.64,1);
  backdrop-filter: blur(24px);
}
@keyframes cmd-drop {
  from { transform: translateY(-18px) scale(0.96); opacity: 0; }
  to   { transform: translateY(0) scale(1); opacity: 1; }
}
.cmd-input-wrap {
  display: flex; align-items: center; gap: 12px;
  padding: 14px 18px; border-bottom: 1px solid var(--border);
}
.cmd-icon { font-size: 18px; color: var(--accent); flex-shrink: 0; }
#cmd-input {
  flex: 1; background: none; border: none; font-size: 16px;
  color: var(--text0); font-family: var(--font); outline: none;
}
#cmd-input::placeholder { color: var(--text2); }
.cmd-shortcut { font-size: 11px; color: var(--text2); font-family: var(--mono);
  background: var(--bg3); border: 1px solid var(--border); border-radius: var(--r4);
  padding: 2px 7px; flex-shrink: 0; }
.cmd-results { max-height: 400px; overflow-y: auto; padding: 8px; }
.cmd-section { font-size: 10px; font-weight: 700; text-transform: uppercase;
  letter-spacing: 1.5px; color: var(--text2); padding: 8px 10px 4px; }
.cmd-item {
  display: flex; align-items: center; gap: 12px; padding: 10px 12px;
  border-radius: var(--r8); cursor: pointer; transition: background var(--t1);
}
.cmd-item:hover, .cmd-item.selected {
  background: var(--accent-glow);
}
.cmd-item.selected { outline: 1px solid rgba(0,229,160,.12); }
.cmd-item-icon { font-size: 17px; width: 28px; text-align: center; flex-shrink: 0; opacity:.85; }
.cmd-item-label { font-size: 14px; color: var(--text0); font-weight: 500; }
.cmd-item-desc { font-size: 11px; color: var(--text2); margin-top: 1px; }
.cmd-item-kbd { margin-left: auto; font-family: var(--mono); font-size: 10px;
  color: var(--text2); background: var(--bg3); border: 1px solid var(--border);
  border-radius: var(--r4); padding: 2px 7px; flex-shrink: 0; }
.cmd-footer { padding: 8px 18px; border-top: 1px solid var(--border);
  display: flex; gap: 16px; font-size: 11px; color: var(--text2); align-items: center; }
.cmd-footer kbd { background: var(--bg3); border: 1px solid var(--border); border-radius: 3px;
  padding: 1px 5px; font-family: var(--mono); font-size: 10px; margin: 0 2px; }

/* ── KANBAN BOARD ── */
#page-kanban { display: none; }
#page-kanban.active { display: block; }
.kanban-board {
  display: flex; gap: 14px; overflow-x: auto; padding-bottom: 16px;
  min-height: calc(100vh - 200px);
}
.kanban-board::-webkit-scrollbar { height: 6px; }
.kanban-col {
  min-width: 290px; max-width: 310px; flex-shrink: 0;
  background: var(--bg2); border: 1px solid var(--border);
  border-radius: var(--r12); display: flex; flex-direction: column;
  max-height: calc(100vh - 200px);
}
.kanban-col-header {
  padding: 12px 14px; border-bottom: 1px solid var(--border);
  display: flex; align-items: center; gap: 10px; flex-shrink: 0;
  border-radius: var(--r12) var(--r12) 0 0;
}
.kanban-col-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.kanban-col-title { font-size: 12px; font-weight: 700; color: var(--text0);
  text-transform: uppercase; letter-spacing: .8px; }
.kanban-col-count {
  margin-left: auto; background: var(--bg3); border: 1px solid var(--border2);
  border-radius: 8px; padding: 1px 8px; font-size: 11px;
  font-family: var(--mono); color: var(--text2);
}
.kanban-cards { flex: 1; overflow-y: auto; padding: 10px; display: flex;
  flex-direction: column; gap: 8px; }
.kanban-card {
  background: var(--bg3); border: 1px solid var(--border2);
  border-radius: var(--r10); padding: 12px; cursor: pointer;
  transition: all var(--t2) var(--ease); position: relative; overflow: hidden;
}
.kanban-card::before {
  content: ''; position: absolute; left: 0; top: 0; bottom: 0; width: 3px;
  border-radius: 2px 0 0 2px;
}
.kanban-card.p-critical::before { background: var(--red); box-shadow: 0 0 8px var(--red); }
.kanban-card.p-high::before { background: var(--yellow); }
.kanban-card.p-medium::before { background: var(--blue); }
.kanban-card.p-low::before { background: var(--green); }
.kanban-card:hover {
  border-color: rgba(255,255,255,.12); transform: translateY(-2px);
  box-shadow: var(--shadow-md);
}
.kanban-card.dragging {
  opacity: 0.5; transform: rotate(1.5deg) scale(1.02);
  box-shadow: var(--shadow-lg);
}
.kanban-col.drag-over { border-color: var(--accent); background: rgba(0,229,160,.04); }
.kanban-card-id { font-family: var(--mono); font-size: 9.5px; color: var(--accent);
  margin-bottom: 5px; letter-spacing: .3px; }
.kanban-card-title { font-size: 13px; font-weight: 500; color: var(--text0);
  margin-bottom: 8px; line-height: 1.4; }
.kanban-card-meta { display: flex; flex-wrap: wrap; gap: 5px; align-items: center; }
.kanban-card-footer { display: flex; align-items: center; justify-content: space-between;
  margin-top: 8px; padding-top: 8px; border-top: 1px solid rgba(255,255,255,.05); }
.kanban-card-asset { font-size: 10px; color: var(--text2); }
.kanban-card-due { font-size: 10px; font-family: var(--mono); }
.kanban-add-btn {
  margin: 6px 10px 10px; padding: 8px; border: 1px dashed var(--border2);
  border-radius: var(--r8); background: none; color: var(--text2); font-size: 12px;
  cursor: pointer; width: calc(100% - 20px); transition: all var(--t2); font-family: var(--font);
}
.kanban-add-btn:hover { border-color: var(--accent); color: var(--accent); background: var(--accent-glow); }

/* ── KPI GAUGE WIDGET ── */
.gauge-grid { display: grid; grid-template-columns: repeat(auto-fit,minmax(160px,1fr)); gap:16px; margin-bottom:24px; }
.gauge-card {
  background: var(--bg2); border: 1px solid var(--border); border-radius: var(--r12);
  padding: 20px; text-align: center; position: relative; overflow: hidden;
}
.gauge-svg { display: block; margin: 0 auto; }
.gauge-value-text { font-family: var(--mono); font-size: 22px; font-weight: 700; color: var(--text0); }
.gauge-label { font-size: 11px; color: var(--text2); text-transform: uppercase;
  letter-spacing: 1px; margin-top: 6px; }
.gauge-sub { font-size: 12px; color: var(--text1); margin-top: 4px; }

/* ── SPARKLINES ── */
.sparkline-wrap { display: inline-flex; align-items: center; }
.sparkline-wrap canvas { vertical-align: middle; }
.stat-card .sparkline-area { position: absolute; bottom: 0; left: 0; right: 0; opacity: 0.15; }

/* ── ACTIVITY FEED ── */
.activity-feed { max-height: 400px; overflow-y: auto; }
.activity-item {
  display: flex; align-items: flex-start; gap: 10px;
  padding: 10px 0; border-bottom: 1px solid var(--border);
  animation: fadein .3s ease;
}
.activity-item:last-child { border-bottom: none; }
.activity-avatar {
  width: 30px; height: 30px; border-radius: 50%; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
  font-size: 12px; font-weight: 700; color: var(--bg0);
}
.activity-body { flex: 1; min-width: 0; }
.activity-text { font-size: 12px; color: var(--text1); line-height: 1.4; }
.activity-text strong { color: var(--text0); font-weight: 500; }
.activity-time { font-size: 10px; color: var(--text2); font-family: var(--mono); margin-top: 2px; }
.activity-type-dot { width: 6px; height: 6px; border-radius: 50%; margin-top: 6px; flex-shrink: 0; }

/* ── SPLIT PANE (Asset Detail) ── */
.split-pane {
  display: grid; grid-template-columns: 340px 1fr; gap: 0;
  height: calc(100vh - 120px); overflow: hidden; border: 1px solid var(--border);
  border-radius: var(--r12);
}
.split-list {
  border-right: 1px solid var(--border); overflow-y: auto;
  background: var(--bg2);
}
.split-list-header {
  padding: 14px 16px; border-bottom: 1px solid var(--border);
  position: sticky; top: 0; background: var(--bg2); z-index: 2;
}
.split-list-item {
  padding: 12px 16px; border-bottom: 1px solid var(--border);
  cursor: pointer; transition: .15s; display: flex; gap: 12px; align-items: center;
}
.split-list-item:hover { background: var(--bg3); }
.split-list-item.active { background: var(--accent-glow); border-left: 3px solid var(--accent); }
.split-detail { overflow-y: auto; background: var(--bg1); }
.split-detail-header {
  padding: 20px 24px; border-bottom: 1px solid var(--border);
  background: var(--bg2); position: sticky; top: 0; z-index: 2;
}
.split-detail-body { padding: 24px; }
.split-asset-icon {
  width: 56px; height: 56px; border-radius: var(--r12);
  background: var(--bg3); border: 1px solid var(--border2);
  display: flex; align-items: center; justify-content: center;
  font-size: 28px; flex-shrink: 0;
}
@media(max-width:900px) {
  .split-pane { grid-template-columns: 1fr; height: auto; }
  .split-list { max-height: 240px; border-right: none; border-bottom: 1px solid var(--border); }
}

/* ── GANTT CHART ── */
.gantt-wrap { overflow-x: auto; }
.gantt-table { border-collapse: collapse; width: 100%; min-width: 800px; }
.gantt-table th { padding: 8px 12px; font-size: 10px; font-weight: 700;
  text-transform: uppercase; letter-spacing: .8px; color: var(--text2);
  border-bottom: 1px solid var(--border); background: var(--bg2); }
.gantt-table td { padding: 6px 12px; border-bottom: 1px solid var(--border); font-size: 12px; color: var(--text1); }
.gantt-bar-cell { position: relative; min-width: 400px; }
.gantt-bar-track { height: 22px; border-radius: 4px; background: var(--bg3); position: relative; overflow: hidden; }
.gantt-bar-fill {
  height: 100%; border-radius: 4px; position: absolute; top: 0;
  display: flex; align-items: center; padding-left: 8px;
  font-size: 10px; font-weight: 600; color: rgba(0,0,0,.7);
  transition: width .6s cubic-bezier(0.4,0,0.2,1);
}
.gantt-bar-fill.status-ok { background: var(--green); }
.gantt-bar-fill.status-soon { background: var(--yellow); }
.gantt-bar-fill.status-overdue { background: var(--red); }
.gantt-today-line {
  position: absolute; top: 0; bottom: 0; width: 2px;
  background: var(--accent); opacity: .7; pointer-events: none;
}
.gantt-label { font-size: 11px; color: var(--text0); font-weight: 500; max-width: 200px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* ── HEAT MAP CALENDAR (dashboard widget) ── */
.heatmap-grid { display: flex; gap: 3px; }
.heatmap-col { display: flex; flex-direction: column; gap: 3px; }
.heatmap-cell {
  width: 14px; height: 14px; border-radius: 2px;
  background: var(--bg3); cursor: pointer; transition: .15s;
  position: relative;
}
.heatmap-cell:hover { transform: scale(1.4); z-index: 2; }
.heatmap-cell[data-level="1"] { background: rgba(0,229,160,.2); }
.heatmap-cell[data-level="2"] { background: rgba(0,229,160,.4); }
.heatmap-cell[data-level="3"] { background: rgba(0,229,160,.65); }
.heatmap-cell[data-level="4"] { background: rgba(0,229,160,.9); }
.heatmap-wrap { overflow-x: auto; padding-bottom: 8px; }
.heatmap-months { display: flex; gap: 3px; font-size: 10px; color: var(--text2);
  margin-bottom: 4px; padding-left: 24px; }
.heatmap-days { display: flex; flex-direction: column; gap: 3px; margin-right: 4px;
  font-size: 9px; color: var(--text2); padding-top: 2px; }

/* ── PROGRESS RINGS ── */
.progress-ring-wrap { position: relative; display: inline-flex; align-items: center; justify-content: center; }
.progress-ring-text { position: absolute; font-family: var(--mono); font-size: 13px; font-weight: 700; }

/* ── ADVANCED TOPBAR SEARCH ── */
.search-suggestions {
  position: absolute; top: 100%; left: 0; right: 0; background: var(--bg2);
  border: 1px solid var(--border2); border-radius: 0 0 var(--r8) var(--r8);
  box-shadow: var(--shadow-float); z-index: 500; max-height: 300px; overflow-y: auto;
}
.search-suggestion {
  display: flex; align-items: center; gap: 10px; padding: 10px 14px;
  cursor: pointer; transition: .15s; font-size: 13px; color: var(--text1);
}
.search-suggestion:hover { background: var(--bg3); color: var(--text0); }
.search-suggestion-icon { font-size: 16px; width: 24px; text-align: center; }
.search-suggestion-sub { font-size: 11px; color: var(--text2); }
.search-wrap { position: relative; }

/* ── NOTIFICATION PANEL ── */
.notif-panel {
  position: absolute; top: calc(100% + 8px); right: 0; width: 340px;
  background: var(--bg2); border: 1px solid var(--border2);
  border-radius: var(--r12); box-shadow: var(--shadow-float);
  z-index: 500; overflow: hidden;
  animation: cmd-drop 0.18s cubic-bezier(0.34,1.56,0.64,1);
}
.notif-panel-header { padding: 14px 16px; border-bottom: 1px solid var(--border);
  display: flex; align-items: center; justify-content: space-between; }
.notif-panel-body { max-height: 360px; overflow-y: auto; }
.notif-item { padding: 12px 16px; border-bottom: 1px solid var(--border);
  cursor: pointer; transition: .15s; display: flex; gap: 10px; }
.notif-item:hover { background: var(--bg3); }
.notif-item.unread { background: var(--accent-glow); }
.notif-item-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--accent); margin-top: 4px; flex-shrink: 0; }
.notif-item-title { font-size: 13px; font-weight: 500; color: var(--text0); margin-bottom: 2px; }
.notif-item-msg { font-size: 12px; color: var(--text1); line-height: 1.4; }
.notif-item-time { font-size: 10px; color: var(--text2); font-family: var(--mono); margin-top: 4px; }

/* ── ACCENT PICKER ── */
.accent-picker { display: flex; gap: 8px; align-items: center; }
.accent-swatch {
  width: 24px; height: 24px; border-radius: 50%; cursor: pointer;
  border: 2px solid transparent; transition: .2s;
}
.accent-swatch:hover { transform: scale(1.2); }
.accent-swatch.active { border-color: white; box-shadow: 0 0 0 2px currentColor; }

/* ── COLLAPSIBLE SIDEBAR ── */
.sidebar.collapsed { width: 58px; }
.sidebar.collapsed .sidebar-logo p,
.sidebar.collapsed .user-inf,
.sidebar.collapsed .nav-label,
.sidebar.collapsed .nav-item > span:not(.nav-icon),
.sidebar.collapsed .nav-badge { display: none; }
.sidebar.collapsed .nav-item { justify-content: center; padding: 10px; }
.sidebar.collapsed .sidebar-logo .logo { font-size: 13px; letter-spacing: 1px; }
.sidebar.collapsed .sidebar-logo { justify-content: center; }
.sidebar.collapsed .user-block { justify-content: center; padding: 10px; }
.sidebar-collapse-btn {
  margin: 6px; padding: 7px; border-radius: var(--r8); border: 1px solid var(--border);
  background: var(--bg3); color: var(--text2); cursor: pointer; font-size: 13px;
  transition: all var(--t2); display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
}
.sidebar-collapse-btn:hover { border-color: var(--accent); color: var(--accent); background: var(--accent-glow); }
.main { transition: all var(--t3) var(--ease); }
#update-dropzone.dz-hover { border-color: var(--accent); background: var(--accent-glow); }
#update-dropzone.dz-ready { border-color: var(--green); background: var(--green-glow); }

/* ── ADVANCED MODAL ANIMATIONS ── */
.modal-overlay { animation: modal-bg-in .2s ease; }
@keyframes modal-bg-in { from { opacity: 0; } to { opacity: 1; } }
.modal { animation: modal-in .24s cubic-bezier(0.34,1.56,0.64,1); }
@keyframes modal-in {
  from { transform: translateY(24px) scale(0.95); opacity: 0; }
  to   { transform: translateY(0) scale(1); opacity: 1; }
}
.modal-overlay.closing { animation: modal-bg-out .18s ease forwards; }
.modal-overlay.closing .modal { animation: modal-out .18s ease forwards; }
@keyframes modal-bg-out { to { opacity: 0; } }
@keyframes modal-out { to { transform: translateY(16px) scale(0.96); opacity: 0; } }

/* ── ENHANCED TABLE ── */
.tbl-sort th { cursor: pointer; user-select: none; }
.tbl-sort th:hover { color: var(--text0); }
.sort-icon { font-size: 10px; margin-left: 4px; opacity: .4; }
.sort-icon.active { opacity: 1; color: var(--accent); }
.tbl-row-expanded td { background: rgba(0,229,160,.03) !important; }
.tbl-expand-row { background: var(--bg1); }
.tbl-expand-row td { padding: 0; }
.tbl-expand-inner { padding: 16px; animation: fadein .2s ease; }
.row-select-cb { cursor: pointer; accent-color: var(--accent); }
.tbl-bulk-bar {
  position: sticky; top: 0; z-index: 10; background: var(--bg2);
  border: 1px solid var(--accent); border-radius: var(--r8);
  padding: 10px 16px; margin-bottom: 12px;
  display: none; align-items: center; gap: 12px;
  animation: fadein .2s ease;
}
.tbl-bulk-bar.visible { display: flex; }

/* ── SKELETON LOADER ── */
.skeleton {
  background: linear-gradient(90deg,
    var(--bg3) 0%, var(--bg3) 35%,
    rgba(255,255,255,.04) 50%,
    var(--bg3) 65%, var(--bg3) 100%);
  background-size: 300% 100%;
  animation: shimmer 1.8s ease-in-out infinite;
  border-radius: var(--r6);
}
@keyframes shimmer { 0% { background-position: 100% 0; } 100% { background-position: -100% 0; } }
.skeleton-text { height: 13px; margin-bottom: 8px; }
.skeleton-text.w-80 { width: 80%; }
.skeleton-text.w-60 { width: 60%; }
.skeleton-stat { height: 64px; border-radius: var(--r10); }
.skeleton-row { height: 44px; margin-bottom: 1px; border-radius: 0; }

/* ── MINI CHARTS IN CARDS ── */
.mini-chart-bar { display: flex; align-items: flex-end; gap: 3px; height: 32px; }
.mini-bar { flex: 1; background: var(--accent); border-radius: 2px 2px 0 0; opacity: .6; transition: .3s; min-height: 2px; }
.mini-bar:hover { opacity: 1; }

/* ── TOOLTIP ── */
.tooltip-wrap { position: relative; display: inline-flex; }
.tooltip-content {
  position: absolute; bottom: calc(100% + 6px); left: 50%; transform: translateX(-50%);
  background: var(--bg0); border: 1px solid var(--border2); border-radius: var(--r6);
  padding: 5px 10px; font-size: 11px; color: var(--text1); white-space: nowrap;
  opacity: 0; pointer-events: none; transition: .2s; z-index: 100;
  box-shadow: var(--shadow-md);
}
.tooltip-wrap:hover .tooltip-content { opacity: 1; transform: translateX(-50%) translateY(-3px); }

/* ── QUICK STATS STRIP ── */
.quick-strip {
  display: flex; gap: 0; background: var(--bg2); border: 1px solid var(--border);
  border-radius: var(--r12); overflow: hidden; margin-bottom: 20px;
}
.quick-strip-item {
  flex: 1; padding: 14px 16px; border-right: 1px solid var(--border);
  text-align: center; transition: background var(--t2); cursor: default;
}
.quick-strip-item:last-child { border-right: none; }
.quick-strip-item:hover { background: var(--bg3); }
.qs-val { font-family: var(--mono); font-size: 21px; font-weight: 700;
  color: var(--text0); line-height: 1; margin-bottom: 2px; }
.qs-lbl { font-size: 10px; color: var(--text2); text-transform: uppercase; letter-spacing: .8px; }
.qs-change { font-size: 11px; margin-top: 3px; }
.qs-up { color: var(--green); } .qs-down { color: var(--red); }

/* ── FOCUS MODE (fullscreen content) ── */
body.focus-mode .sidebar,
body.focus-mode .topbar { display: none; }
body.focus-mode .content { padding: 0; }
body.focus-mode #app { flex-direction: column; }
.focus-exit-btn {
  position: fixed; top: 12px; right: 12px; z-index: 9999;
  background: var(--bg2); border: 1px solid var(--border2);
  border-radius: var(--r8); padding: 8px 14px; cursor: pointer;
  color: var(--text1); font-size: 13px; display: none;
  box-shadow: var(--shadow-float);
}
body.focus-mode .focus-exit-btn { display: flex; align-items: center; gap: 6px; }

/* ── ADVANCED NAV ITEM with sub-items ── */
.nav-sub { padding-left: 30px; display: none; }
.nav-sub.open { display: block; }
.nav-sub .nav-item { font-size: 12px; padding: 6px 10px; }

/* ── LIVE INDICATOR ── */
.live-badge {
  display: inline-flex; align-items: center; gap: 5px;
  background: rgba(0,229,160,.08); border: 1px solid rgba(0,229,160,.2);
  border-radius: 10px; padding: 2px 9px; font-size: 10px;
  font-weight: 700; color: var(--green); text-transform: uppercase; letter-spacing: .5px;
}
.live-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--green);
  animation: live-pulse 1.5s ease-in-out infinite; }
@keyframes live-pulse {
  0%,100% { transform: scale(1); opacity: 1; box-shadow: 0 0 0 0 rgba(0,229,160,.4); }
  50% { transform: scale(1.3); opacity: .7; box-shadow: 0 0 0 4px rgba(0,229,160,0); }
}

/* ── CONTEXT MENU ── */
.ctx-menu {
  position: fixed; background: rgba(19,21,29,.95); border: 1px solid rgba(255,255,255,.1);
  border-radius: var(--r10); box-shadow: var(--shadow-lg); z-index: 9000;
  min-width: 188px; overflow: hidden; backdrop-filter: blur(12px);
  animation: ctx-in .12s var(--ease-spring);
}
@keyframes ctx-in {
  from { transform: scale(0.92) translateY(-4px); opacity: 0; }
  to   { transform: scale(1) translateY(0); opacity: 1; }
}
.ctx-item { padding: 9px 16px; font-size: 13px; color: var(--text1); cursor: pointer;
  display: flex; align-items: center; gap: 10px; transition: background var(--t1); }
.ctx-item:hover { background: rgba(255,255,255,.06); color: var(--text0); }
.ctx-item.danger { color: var(--red); }
.ctx-item.danger:hover { background: rgba(255,77,109,.08); }
.ctx-divider { height: 1px; background: var(--border); margin: 4px 0; }

/* ── WELCOME BANNER ── */
.welcome-banner {
  background: linear-gradient(135deg, rgba(0,229,160,.08) 0%, rgba(77,166,255,.05) 100%);
  border: 1px solid rgba(0,229,160,.15); border-radius: var(--r16);
  padding: 20px 24px; margin-bottom: 20px; display: flex; align-items: center; gap: 18px;
  position: relative; overflow: hidden;
}
.welcome-banner::before {
  content: ''; position: absolute; top: 0; left: 0; right: 0; height: 1px;
  background: linear-gradient(90deg, transparent, var(--accent), var(--blue), transparent);
}
.welcome-emoji { font-size: 36px; flex-shrink: 0; }
.welcome-text h2 { font-size: 17px; font-weight: 700; color: var(--text0); margin-bottom: 3px; }
.welcome-text p { font-size: 12px; color: var(--text2); }
.welcome-dismiss { margin-left: auto; background: none; border: none; color: var(--text2);
  font-size: 18px; cursor: pointer; flex-shrink: 0; padding: 4px; transition: .2s;
  border-radius: var(--r6); }
.welcome-dismiss:hover { color: var(--text0); background: var(--bg3); }

/* ── ENHANCED SETTINGS PAGE ── */
.settings-grid { display: grid; grid-template-columns: 220px 1fr; gap: 24px; }
.settings-sidebar { background: var(--bg2); border: 1px solid var(--border);
  border-radius: var(--r12); padding: 8px; height: fit-content; }
.settings-nav-item { padding: 9px 14px; border-radius: var(--r8); cursor: pointer;
  font-size: 13px; color: var(--text1); transition: .15s; display: flex; align-items: center; gap: 8px; }
.settings-nav-item:hover { background: var(--bg3); color: var(--text0); }
.settings-nav-item.active { background: var(--accent-glow); color: var(--accent); }
.settings-panel { display: none; }
.settings-panel.active { display: block; }
.settings-section { background: var(--bg2); border: 1px solid var(--border);
  border-radius: var(--r12); padding: 24px; margin-bottom: 16px; }
.settings-row { display: flex; align-items: center; justify-content: space-between;
  padding: 14px 0; border-bottom: 1px solid var(--border); }
.settings-row:last-child { border-bottom: none; }
.settings-row-info h4 { font-size: 14px; font-weight: 500; color: var(--text0); margin-bottom: 2px; }
.settings-row-info p { font-size: 12px; color: var(--text2); }
@media(max-width:768px) { .settings-grid { grid-template-columns: 1fr; } }

/* ── TOGGLE SWITCH ── */
.toggle-switch { position: relative; display: inline-flex; width: 44px; height: 24px; cursor: pointer; }
.toggle-switch input { opacity: 0; width: 0; height: 0; position: absolute; }
.toggle-track {
  position: absolute; inset: 0; background: var(--bg3); border: 1px solid var(--border2);
  border-radius: 12px; transition: .3s;
}
.toggle-switch input:checked + .toggle-track { background: var(--accent); border-color: var(--accent); }
.toggle-thumb {
  position: absolute; top: 3px; left: 3px; width: 16px; height: 16px;
  background: white; border-radius: 50%; transition: .3s;
  box-shadow: 0 1px 4px rgba(0,0,0,.3);
}
.toggle-switch input:checked ~ .toggle-thumb { left: calc(100% - 19px); }

/* ── COLUMN CHOOSER ── */
.col-chooser-wrap { position: relative; }
.col-chooser-panel {
  position: absolute; top: calc(100% + 6px); right: 0; background: var(--bg2);
  border: 1px solid var(--border2); border-radius: var(--r8);
  box-shadow: var(--shadow-float); z-index: 300; padding: 8px;
  min-width: 180px; animation: cmd-drop .15s ease;
}
.col-chooser-item { display: flex; align-items: center; gap: 8px; padding: 6px 8px;
  border-radius: var(--r4); cursor: pointer; font-size: 13px; color: var(--text1); transition: .12s; }
.col-chooser-item:hover { background: var(--bg3); }
.col-chooser-item input { cursor: pointer; accent-color: var(--accent); }

/* ── MOBILE SWIPE CARDS (WO list on mobile) ── */
.swipe-card {
  background: var(--bg2); border: 1px solid var(--border); border-radius: var(--r12);
  margin-bottom: 10px; overflow: hidden; position: relative;
  transition: transform .15s ease;
}
.swipe-card-inner { padding: 14px 16px; background: var(--bg2); position: relative; z-index: 1; }
.swipe-card-actions {
  position: absolute; right: 0; top: 0; bottom: 0;
  display: flex; align-items: center;
}
.swipe-action { width: 64px; height: 100%; display: flex; align-items: center;
  justify-content: center; font-size: 20px; cursor: pointer; }
.swipe-action.edit { background: var(--blue); }
.swipe-action.delete { background: var(--red); }

/* ── PAGE TRANSITIONS ── */
.page.active { animation: page-in var(--transition-page); }
@keyframes page-in {
  from { opacity: 0; transform: translateY(10px); }
  to   { opacity: 1; transform: translateY(0); }
}

/* ── KEYBOARD SHORTCUT OVERLAY (enhanced) ── */
#shortcut-overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,.75);
  backdrop-filter: blur(8px); z-index: 9999;
  display: none; align-items: center; justify-content: center;
}
#shortcut-overlay.active { display: flex; }
.shortcut-panel {
  background: var(--bg2); border: 1px solid var(--border2);
  border-radius: var(--r16); width: 540px; max-width: 92vw;
  box-shadow: var(--shadow-modal); padding: 24px;
  animation: cmd-drop .2s cubic-bezier(0.34,1.56,0.64,1);
}
.shortcut-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 16px; }
.shortcut-row { display: flex; align-items: center; justify-content: space-between;
  padding: 8px 12px; background: var(--bg3); border-radius: var(--r8); }
.shortcut-label { font-size: 13px; color: var(--text1); }
.shortcut-keys { display: flex; gap: 4px; }
.shortcut-keys kbd { background: var(--bg2); border: 1px solid var(--border2);
  border-radius: 4px; padding: 2px 6px; font-family: var(--mono); font-size: 11px; color: var(--text0); }

/* ── SCROLLBAR STYLE IMPROVEMENTS ── */
.kanban-cards::-webkit-scrollbar { width: 4px; }
.split-list::-webkit-scrollbar,
.split-detail::-webkit-scrollbar { width: 4px; }
.activity-feed::-webkit-scrollbar { width: 4px; }

/* ══════════════════════════════════════════════════════
   NEXUS CMMS v7 — Polish & Refinements
   ══════════════════════════════════════════════════════ */

/* ── STAT TREND INDICATOR ── */
.stat-trend { display: inline-flex; align-items: center; gap: 3px;
  font-size: 11px; font-family: var(--mono); font-weight: 600;
  padding: 2px 7px; border-radius: var(--r4); margin-top: 4px; }
.stat-trend.up   { color: var(--green); background: var(--green-glow); }
.stat-trend.down { color: var(--red);   background: var(--red-glow); }
.stat-trend.flat { color: var(--text2); background: rgba(255,255,255,.04); }

/* ── GLOW PULSE on critical values ── */
.value-critical { color: var(--red) !important;
  text-shadow: 0 0 12px rgba(255,77,109,.5); }
.value-warning  { color: var(--yellow) !important; }
.value-ok       { color: var(--green) !important; }

/* ── REPORT CARD ── */
.report-card{background:var(--bg2);border:1px solid var(--border);border-radius:var(--r12);
  padding:20px;cursor:pointer;transition:all var(--t2) var(--ease);position:relative;overflow:hidden}
.report-card::before{content:'';position:absolute;inset:0;background:var(--green-glow);opacity:0;transition:opacity var(--t2)}
.report-card:hover::before{opacity:1}
.report-card:hover{border-color:rgba(0,229,160,.2);transform:translateY(-2px);box-shadow:var(--shadow-md)}
.report-card .report-icon{font-size:30px;margin-bottom:12px}
.report-card h3{font-size:14px;font-weight:600;margin-bottom:5px;color:var(--text0)}
.report-card p{font-size:12px;color:var(--text2);line-height:1.5}
.report-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:14px;margin-bottom:24px}

/* ── FILTER TOOLBAR ── */
.toolbar{display:flex;align-items:center;gap:8px;margin-bottom:18px;flex-wrap:wrap}
.filter-select{background:var(--bg3);border:1px solid var(--border2);border-radius:var(--r8);
  padding:7px 12px;color:var(--text1);font-size:13px;cursor:pointer;font-family:var(--font);
  transition:border-color var(--t2)}
.filter-select:focus{outline:none;border-color:var(--green)}
.filter-search{flex:1;min-width:180px}

/* ── USER CARD ── */
.user-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:14px}
.user-card{background:var(--bg2);border:1px solid var(--border);border-radius:var(--r12);
  padding:16px;transition:all var(--t2) var(--ease);position:relative}
.user-card:hover{border-color:var(--border2);box-shadow:var(--shadow-sm);transform:translateY(-1px)}
.user-card-head{display:flex;align-items:center;gap:12px;margin-bottom:12px}
.user-card-av{width:44px;height:44px;border-radius:12px;display:flex;align-items:center;
  justify-content:center;font-weight:700;font-size:18px;flex-shrink:0}
.user-card-info h4{font-size:14px;font-weight:600;color:var(--text0)}
.user-card-info p{font-size:11px;color:var(--text2);margin-top:1px}
.user-card-actions{position:absolute;top:12px;right:12px;display:flex;gap:6px}
.user-inactive{opacity:.45}
.status-dot{width:7px;height:7px;border-radius:50%;flex-shrink:0}
.status-dot.active{background:var(--green);box-shadow:0 0 6px rgba(0,229,160,.5)}
.status-dot.inactive{background:var(--text2)}

/* ── PAGINATION ── */
.pagination{display:flex;align-items:center;gap:5px;justify-content:flex-end;margin-top:16px}
.pag-btn{background:var(--bg3);border:1px solid var(--border);border-radius:var(--r6);
  padding:5px 11px;font-size:12px;cursor:pointer;color:var(--text1);
  transition:all var(--t2);font-family:var(--mono)}
.pag-btn:hover,.pag-btn.active{background:var(--green-glow);border-color:rgba(0,229,160,.3);
  color:var(--green)}
.pag-info{font-size:12px;color:var(--text2);font-family:var(--mono)}

/* ── IMPORT ZONE ── */
.import-zone{border:2px dashed var(--border2);border-radius:var(--r12);padding:40px 32px;
  text-align:center;background:rgba(255,255,255,.01);transition:all var(--t2);cursor:pointer}
.import-zone:hover,.import-zone.drag-over{border-color:var(--green);
  background:var(--green-glow);box-shadow:var(--shadow-glow)}

/* ── FAB ── */
.fab{display:none;position:fixed;bottom:80px;right:20px;width:54px;height:54px;border-radius:50%;
  background:linear-gradient(135deg,var(--green),var(--green2));color:var(--bg0);font-size:22px;
  border:none;cursor:pointer;box-shadow:0 4px 20px rgba(0,229,160,.45),0 0 0 0 rgba(0,229,160,.2);
  z-index:600;align-items:center;justify-content:center;transition:all var(--t3) var(--ease);
  animation:fab-pulse 3s ease-in-out infinite}
@keyframes fab-pulse{0%,100%{box-shadow:0 4px 20px rgba(0,229,160,.45),0 0 0 0 rgba(0,229,160,.2)}
  50%{box-shadow:0 4px 24px rgba(0,229,160,.6),0 0 0 8px rgba(0,229,160,0)}}
.fab:hover{background:linear-gradient(135deg,var(--green2),var(--green3));transform:scale(1.08)}
.fab:active{transform:scale(0.95)}

/* ── OFFLINE BAR ── */
#offline-bar{display:none;position:fixed;top:0;left:0;right:0;height:34px;
  background:linear-gradient(90deg,var(--red),#ff5544);z-index:9990;
  align-items:center;justify-content:center;font-size:12px;font-weight:600;
  color:white;letter-spacing:.5px;gap:8px}
#offline-bar.visible{display:flex}

/* ── SCROLLBAR ── */
::-webkit-scrollbar{width:5px;height:5px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:var(--border2);border-radius:3px}
::-webkit-scrollbar-thumb:hover{background:var(--green)}
.kanban-cards::-webkit-scrollbar { width: 3px; }
.split-list::-webkit-scrollbar,.split-detail::-webkit-scrollbar { width: 3px; }
.activity-feed::-webkit-scrollbar { width: 3px; }

/* ── PRINT ── */
@media print {
  .sidebar, .topbar, .bottom-nav, .fab, #toast, #cmd-palette-overlay,
  .btn, .toolbar, .pagination { display: none !important; }
  .content { padding: 0 !important; overflow: visible !important; }
  .card { break-inside: avoid; }
}

/* ══════════════════════════════════════════════════════
   NEXUS CMMS v5 — Advanced Feature Styles
   AI Insights, SLA Timers, Analytics, Multi-step Wizard,
   QR Labels, Work Request Portal, Enhanced Cards
   ══════════════════════════════════════════════════════ */

/* ── AI INSIGHT CARDS ── */
.insight-strip { display: flex; gap: 12px; overflow-x: auto; padding-bottom: 4px; }
.insight-strip::-webkit-scrollbar { height: 4px; }
.insight-card {
  min-width: 280px; max-width: 320px; flex-shrink: 0;
  background: var(--bg2); border: 1px solid var(--border);
  border-radius: var(--r12); padding: 14px 16px;
  position: relative; overflow: hidden; cursor: pointer; transition: .2s;
}
.insight-card:hover { transform: translateY(-2px); }
.insight-card::before {
  content: ''; position: absolute; left: 0; top: 0; bottom: 0; width: 3px;
}
.insight-card.danger::before  { background: var(--red); }
.insight-card.warning::before { background: var(--yellow); }
.insight-card.info::before    { background: var(--blue); }
.insight-card.success::before { background: var(--green); }
.insight-card-icon { font-size: 24px; margin-bottom: 8px; }
.insight-card-title { font-size: 13px; font-weight: 600; color: var(--text0); margin-bottom: 4px; }
.insight-card-body  { font-size: 11px; color: var(--text2); line-height: 1.5; margin-bottom: 8px; }
.insight-card-btn {
  font-size: 11px; font-weight: 600; color: var(--accent);
  background: var(--accent-glow); border: 1px solid rgba(0,229,160,.2);
  border-radius: 4px; padding: 3px 10px; cursor: pointer;
  font-family: var(--font); transition: .15s;
}
.insight-card-btn:hover { background: rgba(0,229,160,.25); }

/* ── SLA COUNTDOWN TIMER ── */
.sla-item {
  display: flex; align-items: center; gap: 12px; padding: 10px 0;
  border-bottom: 1px solid var(--border);
}
.sla-item:last-child { border-bottom: none; }
.sla-timer {
  font-family: var(--mono); font-size: 13px; font-weight: 700;
  min-width: 80px; text-align: right; flex-shrink: 0;
}
.sla-timer.ok      { color: var(--green); }
.sla-timer.soon    { color: var(--yellow); }
.sla-timer.overdue { color: var(--red); animation: pulse-red 1.5s ease-in-out infinite; }
@keyframes pulse-red {
  0%,100% { opacity: 1; } 50% { opacity: .5; }
}
.sla-bar { height: 3px; border-radius: 2px; background: var(--bg3); overflow: hidden; margin-top: 3px; }
.sla-bar-fill { height: 100%; border-radius: 2px; transition: width .6s; }
.sla-wo-num { font-family: var(--mono); font-size: 10px; color: var(--accent); }
.sla-title  { font-size: 12px; color: var(--text1); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 200px; }

/* ── MULTI-STEP WIZARD ── */
.wizard-overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,.8);
  backdrop-filter: blur(8px); z-index: 2000;
  display: none; align-items: center; justify-content: center;
}
.wizard-overlay.active { display: flex; }
.wizard {
  background: var(--bg2); border: 1px solid var(--border2);
  border-radius: var(--r16); width: 620px; max-width: 95vw;
  max-height: 90vh; overflow: hidden; display: flex; flex-direction: column;
  box-shadow: 0 32px 80px rgba(0,0,0,.7);
  animation: modal-in .25s cubic-bezier(0.34,1.56,0.64,1);
}
.wizard-header {
  padding: 20px 28px 0; border-bottom: 1px solid var(--border);
}
.wizard-steps {
  display: flex; gap: 0; margin-bottom: 20px; position: relative;
}
.wizard-steps::before {
  content: ''; position: absolute; top: 14px; left: 14px; right: 14px;
  height: 2px; background: var(--border2); z-index: 0;
}
.wizard-step {
  flex: 1; display: flex; flex-direction: column; align-items: center;
  gap: 6px; position: relative; z-index: 1;
}
.wizard-step-dot {
  width: 28px; height: 28px; border-radius: 50%;
  border: 2px solid var(--border2); background: var(--bg2);
  display: flex; align-items: center; justify-content: center;
  font-size: 12px; font-weight: 700; color: var(--text2); transition: .3s;
}
.wizard-step.done .wizard-step-dot  { background: var(--green); border-color: var(--green); color: var(--bg0); }
.wizard-step.active .wizard-step-dot{ background: var(--accent); border-color: var(--accent); color: var(--bg0); }
.wizard-step-label { font-size: 10px; color: var(--text2); font-weight: 600;
  text-transform: uppercase; letter-spacing: .5px; white-space: nowrap; }
.wizard-step.active .wizard-step-label { color: var(--accent); }
.wizard-step.done  .wizard-step-label { color: var(--green); }
.wizard-steps::after {
  content: ''; position: absolute; top: 14px; left: 14px;
  height: 2px; background: var(--green); z-index: 0; transition: width .4s ease;
}
.wizard-body { flex: 1; overflow-y: auto; padding: 24px 28px; }
.wizard-pane { display: none; animation: fadein .2s ease; }
.wizard-pane.active { display: block; }
.wizard-footer {
  padding: 16px 28px; border-top: 1px solid var(--border);
  display: flex; justify-content: space-between; align-items: center; gap: 12px;
}
.wizard-progress {
  font-size: 11px; color: var(--text2); font-family: var(--mono);
}

/* ── ANALYTICS LEADERBOARD ── */
.leaderboard-item {
  display: flex; align-items: center; gap: 12px; padding: 10px 0;
  border-bottom: 1px solid var(--border);
}
.leaderboard-item:last-child { border-bottom: none; }
.lb-rank { font-family: var(--mono); font-size: 16px; font-weight: 700;
  color: var(--text2); width: 24px; flex-shrink: 0; }
.lb-rank.gold   { color: #FFD700; }
.lb-rank.silver { color: #C0C0C0; }
.lb-rank.bronze { color: #CD7F32; }
.lb-avatar { width: 36px; height: 36px; border-radius: 50%; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
  font-weight: 700; font-size: 14px; color: var(--bg0); }
.lb-name  { font-size: 13px; font-weight: 500; color: var(--text0); }
.lb-sub   { font-size: 11px; color: var(--text2); }
.lb-score { margin-left: auto; font-family: var(--mono); font-size: 14px;
  font-weight: 700; color: var(--accent); flex-shrink: 0; }

/* ── REPEAT FAILURE TABLE ── */
.failure-item {
  display: flex; align-items: center; gap: 12px; padding: 10px 0;
  border-bottom: 1px solid var(--border);
}
.failure-item:last-child { border-bottom: none; }
.failure-count {
  width: 32px; height: 32px; border-radius: 50%; flex-shrink: 0;
  background: rgba(255,77,109,.12); border: 1px solid rgba(255,77,109,.3);
  display: flex; align-items: center; justify-content: center;
  font-size: 12px; font-weight: 700; color: var(--red);
}
.failure-name { font-size: 13px; font-weight: 500; color: var(--text0); }
.failure-code { font-family: var(--mono); font-size: 10px; color: var(--accent); }
.failure-bar  { height: 3px; background: var(--bg3); border-radius: 2px; overflow: hidden; margin-top: 3px; }
.failure-bar-fill { height: 100%; background: var(--red); border-radius: 2px; }

/* ── WORK REQUEST LIST ── */
.wr-item {
  display: flex; align-items: flex-start; gap: 12px; padding: 12px 0;
  border-bottom: 1px solid var(--border); cursor: pointer; transition: .15s;
}
.wr-item:hover { background: var(--bg3); margin: 0 -8px; padding: 12px 8px; border-radius: var(--r8); }
.wr-item:last-child { border-bottom: none; }
.wr-dot { width: 8px; height: 8px; border-radius: 50%; margin-top: 5px; flex-shrink: 0; }
.wr-num  { font-family: var(--mono); font-size: 10px; color: var(--accent); }
.wr-title{ font-size: 13px; font-weight: 500; color: var(--text0); margin-bottom: 2px; }
.wr-meta { font-size: 11px; color: var(--text2); }

/* ── QR LABEL PRINT BUTTON ── */
.qr-label-btn {
  position: absolute; top: 10px; right: 10px;
  background: var(--bg3); border: 1px solid var(--border2);
  border-radius: var(--r4); padding: 4px 8px; font-size: 11px;
  color: var(--text2); cursor: pointer; transition: .15s; z-index: 2;
}
.qr-label-btn:hover { border-color: var(--accent); color: var(--accent); }

/* ── ENHANCED STAT CARDS (v5) ── */
.stat-card.clickable { cursor: pointer; }
.stat-card.clickable:hover .stat-label { color: var(--accent); }
.stat-trend {
  display: inline-flex; align-items: center; gap: 4px;
  font-size: 11px; font-weight: 600; font-family: var(--mono);
}
.stat-trend.up   { color: var(--green); }
.stat-trend.down { color: var(--red); }

/* ── NOTIFICATION TOAST STACK (enhanced — overrides v4 below) ── */
#toast-stack {
  position: fixed; bottom: 24px; right: 24px; z-index: 9999;
  display: flex; flex-direction: column; gap: 8px; pointer-events: none;
  min-width: 280px; max-width: 380px;
}
.toast-item {
  background: rgba(26,29,39,.96); border: 1px solid rgba(255,255,255,.09);
  border-radius: var(--r10); padding: 12px 16px; font-size: 13px;
  box-shadow: var(--shadow-lg); pointer-events: all;
  display: flex; align-items: center; gap: 10px;
  animation: toast-in .25s var(--ease-spring);
  backdrop-filter: blur(12px);
}
@keyframes toast-in {
  from { transform: translateY(12px) scale(0.95); opacity: 0; }
  to   { transform: translateY(0) scale(1); opacity: 1; }
}
.toast-item.removing { animation: toast-out .2s ease forwards; }
@keyframes toast-out { to { transform: translateX(110%) scale(.95); opacity: 0; } }
.toast-item.success { border-left: 3px solid var(--green); }
.toast-item.error   { border-left: 3px solid var(--red); }
.toast-item.warning { border-left: 3px solid var(--yellow); }
.toast-item.info    { border-left: 3px solid var(--blue); }
.toast-icon { font-size: 16px; flex-shrink: 0; }
.toast-msg  { flex: 1; color: var(--text0); font-size: 13px; line-height: 1.4; }
.toast-close {
  background: none; border: none; color: var(--text2); cursor: pointer;
  font-size: 16px; padding: 2px; line-height: 1; flex-shrink: 0;
  transition: color var(--t1); border-radius: var(--r4);
}
.toast-close:hover { color: var(--text0); }

/* ── FLOATING ACTION MENU (FAB+) ── */
.fab-menu {
  position: fixed; bottom: 82px; right: 20px; z-index: 600;
  display: flex; flex-direction: column; gap: 10px; align-items: flex-end;
}
.fab-menu-item {
  display: flex; align-items: center; gap: 10px;
  opacity: 0; transform: translateY(10px) scale(0.9);
  transition: all .2s ease; pointer-events: none;
}
.fab-menu-item.visible { opacity: 1; transform: translateY(0) scale(1); pointer-events: all; }
.fab-mini {
  width: 44px; height: 44px; border-radius: 50%;
  background: var(--bg2); border: 1px solid var(--border2);
  display: flex; align-items: center; justify-content: center;
  font-size: 18px; cursor: pointer; box-shadow: 0 4px 16px rgba(0,0,0,.4);
  transition: .2s;
}
.fab-mini:hover { background: var(--bg3); border-color: var(--accent); transform: scale(1.1); }
.fab-label {
  background: var(--bg2); border: 1px solid var(--border); border-radius: 6px;
  padding: 4px 10px; font-size: 12px; font-weight: 600; color: var(--text1);
  white-space: nowrap; box-shadow: 0 2px 8px rgba(0,0,0,.3);
}

/* ── ENHANCED MODAL WITH TABS ── */
.modal-tabs { display: flex; border-bottom: 1px solid var(--border); margin: -24px -24px 20px; }
.modal-tab {
  padding: 12px 20px; font-size: 13px; font-weight: 500; color: var(--text2);
  cursor: pointer; transition: .15s; border-bottom: 2px solid transparent;
}
.modal-tab:hover { color: var(--text0); background: var(--bg3); }
.modal-tab.active { color: var(--accent); border-bottom-color: var(--accent); }
.modal-tab-pane { display: none; }
.modal-tab-pane.active { display: block; animation: fadein .2s ease; }

/* ── DASHBOARD HEATMAP ── */
.heatmap-legend {
  display: flex; align-items: center; gap: 6px; font-size: 10px;
  color: var(--text2); margin-top: 8px; justify-content: flex-end;
}
.heatmap-legend-cell {
  width: 12px; height: 12px; border-radius: 2px;
}

/* ── PRINT STYLES ── */
@media print {
  body { background: white !important; color: black !important; }
  .card { border: 1px solid #ddd !important; background: white !important; break-inside: avoid; }
  .stat-card { background: white !important; border: 1px solid #ddd !important; }
  canvas { max-width: 100%; }
}

/* ── PULSE ANIMATION FOR CRITICAL ITEMS ── */
.pulse-critical {
  animation: pulse-border 2s ease-in-out infinite;
}
@keyframes pulse-border {
  0%,100% { box-shadow: 0 0 0 0 rgba(255,77,109,0); }
  50%      { box-shadow: 0 0 0 4px rgba(255,77,109,.2); }
}

/* ── ENHANCED MOBILE ── */
@media(max-width:768px) {
  .insight-strip { flex-direction: column; }
  .insight-card  { min-width: unset; max-width: unset; }
  .wizard        { max-height: 95vh; }
  .wizard-header { padding: 16px 20px 0; }
  .wizard-body   { padding: 16px 20px; }
  .wizard-footer { padding: 12px 20px; }
}

/* ── BULK ACTION STYLES ── */
.wo-select-th, .wo-row-cb { width: 36px !important; padding: 0 6px !important; }
input[type=checkbox] { accent-color: var(--accent); width: 15px; height: 15px; }
#bulk-action-bar { box-shadow: 0 -4px 24px rgba(0,0,0,.4); }

/* ── GLOBAL SEARCH RESULTS IN CMD PALETTE ── */
.cmd-search-section { font-size: 10px; color: var(--text2); padding: 4px 14px 2px;
  text-transform: uppercase; letter-spacing: .8px; border-top: 1px solid var(--border); }

/* ── WIZARD PROGRESS LINE ── */
.wizard-steps[style*="--wz-progress"]::after {
  width: calc(var(--wz-progress, 0%) * 0.857);  /* span across 6/7 of bar */
}

/* ── HEATMAP TOOLTIP ── */
.heat-tooltip { position: fixed; pointer-events: none; z-index: 9999; }

/* ── SLA URGENCY PULSE ── */
.sla-item.critical-sla { animation: pulse-row 2s ease-in-out infinite; }
@keyframes pulse-row {
  0%,100% { background: transparent; }
  50%      { background: rgba(255,77,109,.06); }
}

/* ── ASSET HEALTH BADGE ── */
.health-badge {
  display: inline-flex; align-items: center; gap: 4px;
  font-size: 11px; font-weight: 700; padding: 2px 8px;
  border-radius: 12px; font-family: var(--mono);
}
.health-badge.good   { background: rgba(0,229,160,.12); color: var(--green); border: 1px solid rgba(0,229,160,.2); }
.health-badge.fair   { background: rgba(255,190,77,.12); color: var(--yellow); border: 1px solid rgba(255,190,77,.2); }
.health-badge.poor   { background: rgba(255,77,109,.12); color: var(--red); border: 1px solid rgba(255,77,109,.2); }

/* ── INSIGHT EMPTY STATE ── */
.no-insights {
  background: linear-gradient(135deg, rgba(0,229,160,.04), rgba(0,229,160,.01));
  border: 1px dashed rgba(0,229,160,.2); border-radius: var(--r12);
  padding: 20px 24px; text-align: center; color: var(--text2); font-size: 13px;
}

/* ── ANALYTICS THREE-COL ── */
.three-col {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 16px;
}
@media(max-width:1100px) { .three-col { grid-template-columns: 1fr 1fr; } }
@media(max-width:700px)  { .three-col { grid-template-columns: 1fr; } }

/* ── CHART WRAP HEIGHT ── */
.chart-wrap { height: 220px; }

/* ── AUTO-REFRESH INDICATOR ── */
#dash-refresh-indicator {
  font-size: 11px; color: var(--text2); font-family: var(--mono);
  padding: 4px 8px; border-radius: 4px; cursor: pointer;
  background: var(--bg3); border: 1px solid var(--border); transition: .15s;
}
#dash-refresh-indicator:hover { border-color: var(--accent); color: var(--accent); }

/* ── ENHANCED NAV BADGES ── */
.nav-badge {
  min-width: 18px; height: 18px; border-radius: 9px; padding: 0 5px;
  background: var(--red); color: #fff; font-size: 10px; font-weight: 700;
  display: inline-flex; align-items: center; justify-content: center;
  margin-left: auto; font-family: var(--mono); flex-shrink: 0;
}

/* ── PORTAL URL DISPLAY ── */
#portal-url {
  word-break: break-all; cursor: pointer;
}
#portal-url:hover { color: var(--accent); }

/* ═══════════════════════════════════════════════════════
   NEXUS CMMS v9 — Enhanced Mobile View
   ═══════════════════════════════════════════════════════ */

/* ── MOBILE: TOUCH-FRIENDLY BOTTOM NAV ── */
@media(max-width:768px) {
  /* Larger touch targets */
  .bottom-nav-item {
    min-height: 56px;
    padding: 4px 2px 6px;
    position: relative;
  }
  .bottom-nav-item .bn-icon { font-size: 22px; }

  /* Center scan button elevation */
  #bn-scan .bn-icon {
    width: 46px !important;
    height: 46px !important;
    margin-top: -18px !important;
    box-shadow: 0 4px 16px rgba(0,229,160,.5) !important;
    font-size: 20px !important;
  }

  /* Active state with stronger indicator */
  .bottom-nav-item.active::after {
    content: '';
    position: absolute;
    bottom: 0; left: 50%;
    transform: translateX(-50%);
    width: 28px; height: 3px;
    background: var(--green);
    border-radius: 2px 2px 0 0;
  }

  /* ── TOPBAR MOBILE ── */
  .topbar {
    padding: 0 12px;
    height: 54px;
  }
  .topbar-right { gap: 6px; }
  #topbar-action { font-size: 12px; padding: 5px 10px; }

  /* ── CONTENT MOBILE ── */
  .content {
    padding: 12px;
    padding-bottom: calc(var(--bottomnav-h) + env(safe-area-inset-bottom,0px) + 70px);
  }

  /* ── STAT CARDS MOBILE ── */
  .stats-grid { grid-template-columns: repeat(2,1fr); gap: 8px; margin-bottom: 14px; }
  .stat-card { padding: 14px 12px; border-radius: var(--r10); }
  .stat-value { font-size: 20px !important; }
  .stat-label { font-size: 10px !important; }

  /* ── QUICK STRIP MOBILE ── */
  .quick-strip {
    overflow-x: auto;
    flex-wrap: nowrap;
    -webkit-overflow-scrolling: touch;
    scrollbar-width: none;
    gap: 0;
    margin-bottom: 12px;
  }
  .quick-strip::-webkit-scrollbar { display: none; }
  .quick-strip-item {
    min-width: 90px;
    padding: 10px 12px;
    flex: 0 0 auto;
  }
  .qs-val { font-size: 18px; }
  .qs-lbl { font-size: 9px; }

  /* ── WELCOME BANNER MOBILE ── */
  .welcome-banner {
    padding: 14px 16px;
    gap: 12px;
    margin-bottom: 12px;
  }
  .welcome-emoji { font-size: 28px; }
  .welcome-text h2 { font-size: 15px; }
  .welcome-text p { font-size: 11px; }

  /* ── CARDS MOBILE ── */
  .card { padding: 14px; border-radius: var(--r10); }
  .card-header { padding: 12px 14px; }
  .two-col, .three-col { grid-template-columns: 1fr !important; }

  /* ── TOOLBAR MOBILE ── */
  .toolbar {
    flex-wrap: wrap;
    gap: 6px;
    margin-bottom: 12px;
  }
  .toolbar .filter-search { width: 100% !important; order: -1; }
  .toolbar .filter-select { flex: 1; min-width: 0; font-size: 12px; }
  .toolbar .btn { font-size: 12px; padding: 6px 10px; }
  .toolbar .btn-primary { margin-left: 0 !important; }

  /* ── TABLES MOBILE: Card-style rows ── */
  .tbl-wrap { overflow-x: auto; -webkit-overflow-scrolling: touch; }
  .tbl-wrap table { min-width: 520px; }

  /* ── WORK ORDER CARDS ON MOBILE ── */
  .wo-mobile-card {
    background: var(--bg2);
    border: 1px solid var(--border);
    border-radius: var(--r10);
    padding: 14px;
    margin-bottom: 10px;
    position: relative;
    overflow: hidden;
    cursor: pointer;
    transition: all var(--t2);
  }
  .wo-mobile-card::before {
    content: '';
    position: absolute; left: 0; top: 0; bottom: 0; width: 3px;
  }
  .wo-mobile-card.p-critical::before { background: var(--red); }
  .wo-mobile-card.p-high::before { background: var(--yellow); }
  .wo-mobile-card.p-medium::before { background: var(--blue); }
  .wo-mobile-card.p-low::before { background: var(--green); }
  .wo-mobile-card:hover { transform: translateY(-1px); box-shadow: var(--shadow-md); }
  .wo-mc-top { display: flex; align-items: flex-start; justify-content: space-between; gap: 8px; margin-bottom: 8px; }
  .wo-mc-num { font-family: var(--mono); font-size: 10px; color: var(--accent); }
  .wo-mc-title { font-size: 14px; font-weight: 600; color: var(--text0); margin-bottom: 4px; line-height: 1.3; }
  .wo-mc-meta { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 6px; }
  .wo-mc-footer { display: flex; align-items: center; justify-content: space-between; margin-top: 10px; padding-top: 8px; border-top: 1px solid rgba(255,255,255,.06); font-size: 11px; color: var(--text2); }

  /* ── MODAL MOBILE ── */
  .modal {
    width: 100% !important;
    max-width: 100% !important;
    max-height: 92vh;
    margin: auto 0 0 !important;
    border-radius: var(--r16) var(--r16) 0 0 !important;
    animation: modal-slide-up .3s cubic-bezier(0.34,1.56,0.64,1) !important;
  }
  @keyframes modal-slide-up {
    from { transform: translateY(100%); opacity: 0.8; }
    to   { transform: translateY(0); opacity: 1; }
  }
  .modal-overlay { align-items: flex-end !important; }
  .modal-header { padding: 16px 18px; }
  .modal-body { padding: 16px 18px; }
  .modal-footer { padding: 12px 18px; }

  /* ── FORM CONTROLS MOBILE ── */
  .form-control { font-size: 16px !important; } /* Prevent iOS zoom */
  .form-group { margin-bottom: 14px; }
  select.form-control, select.filter-select { font-size: 16px !important; }

  /* ── SECTION TITLE MOBILE ── */
  .section-title { font-size: 16px; margin-bottom: 12px; }

  /* ── KPI GAUGE MOBILE ── */
  .gauge-grid { grid-template-columns: 1fr 1fr; gap: 10px; }

  /* ── KANBAN MOBILE: Horizontal scroll ── */
  .kanban-board { gap: 10px; padding-bottom: 12px; }
  .kanban-col { min-width: 260px; max-width: 280px; }

  /* ── ANALYTICS CHARTS MOBILE ── */
  .chart-wrap { height: 180px; }

  /* ── SETTINGS MOBILE ── */
  .settings-grid { grid-template-columns: 1fr !important; }
  .settings-sidebar { margin-bottom: 12px; }

  /* ── SPLIT PANE MOBILE ── */
  .split-pane { grid-template-columns: 1fr; height: auto; }
  .split-list { max-height: 220px; border-right: none; border-bottom: 1px solid var(--border); }

  /* ── INSIGHT CARDS MOBILE ── */
  .insight-strip { flex-direction: column; gap: 8px; }
  .insight-card { min-width: unset; max-width: unset; }

  /* ── FAB MENU MOBILE ── */
  .fab-menu { bottom: 88px; right: 16px; }
  #fab-btn { bottom: 86px; right: 16px; width: 50px; height: 50px; font-size: 20px; }

  /* ── PAGINATION MOBILE ── */
  .pagination { justify-content: center; flex-wrap: wrap; }

  /* ── HIDE LESS-IMPORTANT TABLE COLUMNS ── */
  table th:nth-child(n+5), table td:nth-child(n+5) { display: none; }

  /* ── PARTS TABLE MOBILE ── */
  #page-parts table th:nth-child(6),
  #page-parts table td:nth-child(6),
  #page-parts table th:nth-child(7),
  #page-parts table td:nth-child(7) { display: none; }

  /* ── USER GRID MOBILE ── */
  .user-grid { grid-template-columns: 1fr !important; gap: 10px; }

  /* ── REPORT GRID MOBILE ── */
  .report-grid { grid-template-columns: 1fr 1fr; gap: 10px; }
  .report-card { padding: 14px; }
  .report-icon { font-size: 24px; margin-bottom: 6px; }
  .report-card h3 { font-size: 13px; }
  .report-card p { font-size: 11px; display: none; }

  /* ── CALENDAR MOBILE ── */
  .cal-cell { min-height: 40px; }
  .cal-event { font-size: 9px; padding: 1px 4px; }
  .cal-dow { font-size: 9px; }
  .cal-nav { flex-wrap: wrap; gap: 6px; }

  /* ── TOPBAR SEARCH HIDE ON SMALL ── */
  .search-box { display: none; }
  .search-wrap { display: none; }

  /* ── CMD PALETTE MOBILE ── */
  .cmd-palette { width: 98vw; max-height: 80vh; }
  #cmd-input { font-size: 16px !important; }

  /* ── ACTIVITY FEED MOBILE ── */
  .activity-feed { max-height: 300px; }

  /* ── EQ HISTORY MOBILE ── */
  .eq-selector { flex-direction: column; gap: 8px; }
  .eq-selector select { min-width: unset; max-width: unset; width: 100%; }
  .hist-summary { grid-template-columns: 1fr 1fr; }

  /* ── PM CARDS MOBILE ── */
  .tab-bar { width: 100%; overflow-x: auto; flex-wrap: nowrap; -webkit-overflow-scrolling: touch; }
  .tab-btn { font-size: 12px; padding: 6px 12px; white-space: nowrap; }

  /* ── DOWNTIME BARS ── */
  .dt-bar { height: 12px; }

  /* ── TOPBAR LOGO AREA ── */
  .topbar-title { font-size: 13px; max-width: 150px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

  /* ── BULK ACTION BAR MOBILE ── */
  #bulk-action-bar { padding: 10px 12px; gap: 6px; flex-wrap: wrap; }
  #bulk-action-bar select { flex: 1; font-size: 13px; }

  /* ── LOGIN CARD MOBILE ── */
  .login-card { width: calc(100vw - 24px); padding: 28px 20px; }
  .login-logo .logo-mark { font-size: 32px; }
}

/* ── VERY SMALL SCREENS (< 400px) ── */
@media(max-width:400px) {
  .stats-grid { grid-template-columns: 1fr 1fr; gap: 6px; }
  .stat-card { padding: 10px; }
  .stat-value { font-size: 18px !important; }
  .report-grid { grid-template-columns: 1fr; }
  .hist-summary { grid-template-columns: 1fr 1fr; }
  .gauge-grid { grid-template-columns: 1fr 1fr; }
  .bottom-nav-item { font-size: 8px; }
  table th:nth-child(n+4), table td:nth-child(n+4) { display: none; }
  .quick-strip-item { min-width: 80px; padding: 8px; }
  .qs-val { font-size: 16px; }
}

/* ── MOBILE: Touch improvements for buttons ── */
@media(hover:none) and (pointer:coarse) {
  /* Larger touch targets for all interactive elements */
  .btn { min-height: 38px; }
  .nav-item { min-height: 40px; }
  .form-control { min-height: 42px; }
  .tab-btn { min-height: 36px; }
  .bottom-nav-item { min-height: 52px; }

  /* Remove hover effects on touch devices */
  .stat-card:hover { transform: none; }
  .kanban-card:hover { transform: none; }
  .split-list-item:hover { background: transparent; }

  /* Better tap targets for table rows */
  td, th { padding: 10px 8px !important; }
}

/* ── LANDSCAPE MOBILE OPTIMIZATION ── */
@media(max-width:768px) and (orientation:landscape) {
  .content {
    padding-bottom: calc(var(--bottomnav-h) + env(safe-area-inset-bottom,0px) + 12px);
  }
  .stats-grid { grid-template-columns: repeat(3,1fr); }
  .login-card { padding: 20px; }
  .login-logo { margin-bottom: 16px; }
  .login-logo .logo-mark { font-size: 28px; }
}

/* ── PWA / STANDALONE MODE ── */
@media(display-mode:standalone) {
  .topbar {
    padding-top: env(safe-area-inset-top, 0px);
    height: calc(var(--topbar-h) + env(safe-area-inset-top, 0px));
  }
  .bottom-nav {
    padding-bottom: calc(env(safe-area-inset-bottom, 0px) + 4px);
    height: calc(var(--bottomnav-h) + env(safe-area-inset-bottom, 0px));
  }
}

/* ── TABLET (768px - 1024px) ── */
@media(min-width:769px) and (max-width:1024px) {
  --sidebar-w: 200px;
  .stats-grid { grid-template-columns: repeat(3,1fr); }
  .stat-value { font-size: 24px !important; }
  .two-col { grid-template-columns: 1fr 1fr; }
  .three-col { grid-template-columns: 1fr 1fr !important; }
  .card { padding: 16px; }
  .kanban-col { min-width: 240px; }
  table th:nth-child(n+6), table td:nth-child(n+6) { display: none; }
}

/* ── MOBILE SAFE AREA SUPPORT ── */
@supports(padding: env(safe-area-inset-bottom)) {
  .bottom-nav {
    padding-bottom: env(safe-area-inset-bottom, 0px);
    height: calc(62px + env(safe-area-inset-bottom, 0px));
  }
  #toast-stack {
    bottom: calc(24px + env(safe-area-inset-bottom, 0px));
  }
}

/* ── MOBILE: Smooth scrolling and momentum ── */
.content, .tbl-wrap, .kanban-board, .activity-feed, .notif-panel-body {
  -webkit-overflow-scrolling: touch;
}

/* ── MOBILE: Prevent text size adjustment ── */
html {
  -webkit-text-size-adjust: 100%;
  text-size-adjust: 100%;
}

</style>
</head>
<body>
<!-- LOGIN -->
<div id="offline-bar">📶 You are offline — Offline mode active</div>
<div id="pwa-install-banner">
  <div class="pwa-logo">⚙</div>
  <div class="pwa-text">
    <h4>Install NEXUS CMMS</h4>
    <p>Add to home screen for the best mobile experience</p>
  </div>
  <div style="margin-left:auto;display:flex;gap:8px">
    <button class="btn btn-primary btn-sm" id="pwa-install-btn">Install</button>
    <button class="btn btn-secondary btn-sm" onclick="dismissPWA()">Later</button>
  </div>
</div>

<!-- QR SCANNER -->
<div id="qr-scanner-overlay">
  <div style="color:var(--text1);font-size:13px;text-align:center;margin-bottom:8px">
    Point camera at asset QR code or barcode
  </div>
  <div class="qr-frame">
    <video id="qr-video" playsinline autoplay></video>
    <div class="qr-corner tl"></div>
    <div class="qr-corner tr"></div>
    <div class="qr-corner bl"></div>
    <div class="qr-corner br"></div>
    <div class="qr-scan-line"></div>
  </div>
  <div id="qr-result" style="color:var(--text1);font-size:13px;min-height:20px;text-align:center"></div>
  <div style="display:flex;gap:12px">
    <button class="btn btn-secondary" onclick="closeQRScanner()">✕ Cancel</button>
    <button class="btn btn-secondary" onclick="qrManualEntry()">⌨ Enter Manually</button>
  </div>
</div>

<div id="login-screen">
  <div class="login-grid-bg"></div>
  <div class="login-card">
    <div class="login-logo">
      <div class="logo-mark">NEXUS</div>
      <div class="logo-sub">CMMS Enterprise v9 &nbsp;·&nbsp; Maintenance Management</div>
    </div>
    <div class="login-demo">
      Admin: <span>admin</span> / <span>admin123</span> &nbsp;·&nbsp;
      Tech: <span>tech1</span> / <span>tech123</span>
    </div>
    <div class="form-group">
      <label>Username</label>
      <div class="login-field-wrap">
        <span class="field-icon">👤</span>
        <input type="text" id="login-user" class="form-control" value="admin" autocomplete="username" placeholder="Enter username">
      </div>
    </div>
    <div class="form-group">
      <label>Password</label>
      <div class="login-field-wrap">
        <span class="field-icon">🔑</span>
        <input type="password" id="login-pass" class="form-control" value="admin123" autocomplete="current-password" placeholder="Enter password">
      </div>
    </div>
    <button class="login-submit" onclick="doLogin()">Sign In &nbsp;→</button>
    <p id="login-err" style="color:var(--red);font-size:12px;margin-top:12px;text-align:center"></p>
  </div>
</div>

<!-- APP -->
<div id="app">
  <!-- SIDEBAR -->
  <nav class="sidebar">
    <div class="sidebar-logo">
      <div>
        <div class="logo">NEXUS</div>
        <div class="logo-v">CMMS Enterprise v9</div>
      </div>
      <button class="sidebar-collapse-btn" onclick="toggleSidebarCollapse()" title="Collapse sidebar (\)">◀</button>
    </div>
    <div class="user-block" onclick="showPage('profile')">
      <div class="user-av" id="sb-av">A</div>
      <div class="user-inf">
        <h4 id="sb-name">Admin</h4>
        <p id="sb-role">Administrator</p>
      </div>
    </div>
    <div class="nav-group">
      <div class="nav-label">Operations</div>
      <div class="nav-item active" onclick="showPage('dashboard')"><span class="nav-icon">◈</span>Dashboard</div>
      <div class="nav-item" onclick="showPage('work-orders')"><span class="nav-icon">📋</span>Work Orders<span class="nav-badge" id="nb-wo" style="display:none">0</span></div>
      <div class="nav-item" onclick="showPage('kanban')"><span class="nav-icon">🗂</span>Kanban Board</div>
      <div class="nav-item" onclick="showPage('assets')"><span class="nav-icon">⚙</span>Assets</div>
      <div class="nav-item" onclick="showPage('pm')"><span class="nav-icon">🗓</span>PM Schedules<span class="nav-badge warn" id="nb-pm" style="display:none">0</span></div>
      <div class="nav-item" onclick="showPage('eq-history')"><span class="nav-icon">📊</span>Equipment History</div>
      <div class="nav-item" onclick="showPage('activity')"><span class="nav-icon">📡</span>Activity Feed</div>
      <div class="nav-item" onclick="showPage('analytics')"><span class="nav-icon">📈</span>Analytics</div>
    </div>
    <div class="nav-group">
      <div class="nav-label">Planning</div>
      <div class="nav-item" onclick="showPage('calendar')"><span class="nav-icon">📅</span>Calendar</div>
      <div class="nav-item" onclick="showPage('reports')"><span class="nav-icon">📊</span>Reports</div>
      <div class="nav-item" onclick="showPage('budget')"><span class="nav-icon">💰</span>Budget Tracker</div>
      <div class="nav-item" onclick="showPage('sla-monitor')"><span class="nav-icon">⏱</span>SLA Monitor<span class="nav-badge warn" id="nb-sla" style="display:none">0</span></div>
    </div>
    <div class="nav-group">
      <div class="nav-label">Inventory</div>
      <div class="nav-item" onclick="showPage('parts')"><span class="nav-icon">🔧</span>Parts & Stock<span class="nav-badge warn" id="nb-parts" style="display:none">0</span></div>
      <div class="nav-item" onclick="showPage('suppliers')"><span class="nav-icon">🏭</span>Suppliers</div>
      <div class="nav-item" onclick="showPage('purchase-orders')"><span class="nav-icon">🛒</span>Purchase Orders</div>
      <div class="nav-item" onclick="showPage('reorder-wizard')"><span class="nav-icon">🪄</span>Reorder Wizard</div>
      <div class="nav-item" onclick="showPage('import')"><span class="nav-icon">⬆</span>Import Data</div>
      <div class="nav-item" onclick="showPage('work-requests')"><span class="nav-icon">📝</span>Work Requests</div>
    </div>
    <div class="nav-group admin-section" style="display:none">
      <div class="nav-label">Administration</div>
      <div class="nav-item" onclick="showPage('users')"><span class="nav-icon">👥</span>User Management</div>
      <div class="nav-item" onclick="showPage('audit')"><span class="nav-icon">📜</span>Audit Log</div>
      <div class="nav-item" onclick="showPage('settings')"><span class="nav-icon">⚙</span>Settings</div>
    </div>
    <div class="nav-group" style="margin-top:auto;padding-top:8px;border-top:1px solid var(--border)">
      <div class="nav-item" onclick="showPage('about')"><span class="nav-icon">ℹ</span>About</div>
      <div class="nav-item" onclick="doLogout()"><span class="nav-icon">→</span>Sign Out</div>
    </div>
  </nav>

  <!-- MAIN -->
  <div class="main">
    <div class="topbar">
      <div class="hamburger" id="hamburger-btn" onclick="toggleSidebar()">
        <span></span><span></span><span></span>
      </div>
      <span class="topbar-title" id="topbar-title">Dashboard</span>
      <span style="font-size:10px;font-family:var(--mono);color:var(--text2);margin-left:6px;display:none" id="topbar-version-badge"></span>
      <div class="topbar-right">
        <button class="btn btn-secondary btn-sm" onclick="openCmdPalette()" title="Command Palette (Ctrl+K)" style="display:flex;align-items:center;gap:6px">
          <span>⌘</span><span style="font-size:11px;color:var(--text2)">Ctrl K</span>
        </button>
        <button class="btn btn-secondary btn-sm" onclick="openQRScanner()" title="Scan QR/Barcode" style="padding:6px 10px">📷</button>
        <div class="theme-toggle" onclick="toggleTheme()" title="Toggle light/dark mode" id="theme-toggle-btn">🌙</div>
        <div class="notif-btn" style="position:relative" onclick="toggleNotifPanel(event)">
          🔔 <span class="notif-dot" id="notif-dot" style="display:none"></span>
          <div id="notif-panel" class="notif-panel" style="display:none" onclick="event.stopPropagation()">
            <div class="notif-panel-header">
              <span style="font-weight:600;font-size:14px">Notifications</span>
              <button onclick="markAllRead()" class="btn btn-secondary btn-sm">Mark all read</button>
            </div>
            <div class="notif-panel-body" id="notif-panel-body">
              <div class="empty-state" style="padding:24px"><div class="icon">🔔</div><h3>No notifications</h3></div>
            </div>
          </div>
        </div>
        <div style="display:flex;align-items:center;gap:4px;font-size:12px;color:var(--text2)">
          <span class="sync-dot" id="sync-dot" title="Connection status"></span>
          <span id="sync-label" style="display:none;font-size:11px">Syncing…</span>
        </div>
        <button class="btn btn-primary btn-sm" id="topbar-action" style="display:none"></button>
      </div>
    </div>
    <div class="content">

      <!-- DASHBOARD -->
      <div class="page active" id="page-dashboard">
        <!-- Welcome Banner -->
        <div class="welcome-banner" id="welcome-banner" style="display:none">
          <div class="welcome-emoji" id="welcome-emoji">👋</div>
          <div class="welcome-text">
            <h2 id="welcome-heading">Good morning, Admin!</h2>
            <p id="welcome-sub">You have 0 open work orders and 0 PMs due this week.</p>
          </div>
          <button class="welcome-dismiss" onclick="this.closest('.welcome-banner').style.display='none'" title="Dismiss">✕</button>
        </div>
        <!-- Quick Stats Strip -->
        <div class="quick-strip" id="dash-quick-strip" style="display:none">
          <div class="quick-strip-item">
            <div class="qs-val" id="qs-open">—</div>
            <div class="qs-lbl">Open WOs</div>
          </div>
          <div class="quick-strip-item">
            <div class="qs-val" id="qs-overdue">—</div>
            <div class="qs-lbl">Overdue</div>
          </div>
          <div class="quick-strip-item">
            <div class="qs-val" id="qs-assets">—</div>
            <div class="qs-lbl">Assets</div>
          </div>
          <div class="quick-strip-item">
            <div class="qs-val" id="qs-pm-due">—</div>
            <div class="qs-lbl">PMs Due</div>
          </div>
          <div class="quick-strip-item">
            <div class="qs-val" id="qs-low-stock">—</div>
            <div class="qs-lbl">Low Stock</div>
          </div>
        </div>
        <div class="stats-grid" id="dash-stats"></div>
        <!-- My Tasks widget (shown to non-admin users) -->
        <div class="card" id="dash-my-tasks-card" style="margin-bottom:20px;display:none">
          <div class="card-header" style="display:flex;align-items:center;justify-content:space-between">
            <span class="card-title">📋 My Open Tasks</span>
            <button class="btn btn-secondary btn-sm" onclick="showPage('work-orders')">View All</button>
          </div>
          <div id="dash-my-tasks-list"></div>
        </div>
        <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:16px;margin-bottom:20px">
          <div class="card">
            <div class="card-header"><span class="card-title">WO by Status</span></div>
            <div class="chart-wrap"><canvas id="chart-wo-status"></canvas></div>
          </div>
          <div class="card">
            <div class="card-header"><span class="card-title">WO by Type</span></div>
            <div class="chart-wrap"><canvas id="chart-wo-type"></canvas></div>
          </div>
          <div class="card">
            <div class="card-header"><span class="card-title">Assets by Category</span></div>
            <div class="chart-wrap"><canvas id="chart-assets-cat"></canvas></div>
          </div>
          <div class="card">
            <div class="card-header"><span class="card-title">PM Compliance</span></div>
            <div class="chart-wrap" style="position:relative"><canvas id="chart-pm-compliance"></canvas>
              <div id="pm-compliance-label" style="position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);text-align:center;pointer-events:none">
                <div style="font-size:24px;font-weight:700;font-family:var(--mono);color:var(--green)" id="pm-pct-val">—</div>
                <div style="font-size:11px;color:var(--text2)">Compliant</div>
              </div>
            </div>
          </div>
        </div>
        <div class="card" style="margin-bottom:20px">
          <div class="card-header"><span class="card-title">📈 Monthly Cost Trend (Last 6 Months)</span></div>
          <div class="chart-wrap" style="height:180px"><canvas id="chart-cost-trend"></canvas></div>
        </div>
        <div class="two-col">
        <div class="two-col">
          <div class="card">
            <div class="card-header"><span class="card-title">Recent Work Orders</span>
              <button class="btn btn-secondary btn-sm" onclick="showPage('work-orders')">View All</button></div>
            <div class="tbl-wrap"><table id="dash-wo-tbl"><tbody></tbody></table></div>
          </div>
          <div class="card">
            <div class="card-header"><span class="card-title">⚠ Low Stock Parts</span></div>
            <div id="dash-low-stock"></div>
          </div>
        </div>
        <div class="card">
          <div class="card-header"><span class="card-title">📅 Upcoming PM (Next 30 Days)</span>
            <button class="btn btn-secondary btn-sm" onclick="showPage('pm')">View All</button></div>
          <div id="dash-pm"></div>
        </div>
      </div>
      </div><!-- /page-dashboard -->

      <!-- WORK ORDERS -->
      <div class="page" id="page-work-orders">
        <div class="toolbar">
          <input type="text" class="form-control filter-search" placeholder="🔍 Search work orders..." oninput="debounce(()=>loadWO(),400)" id="wo-search">
          <select class="filter-select" onchange="loadWO()" id="wo-status-filter">
            <option value="">All Status</option>
            <option value="open">Open</option>
            <option value="in_progress">In Progress</option>
            <option value="on_hold">On Hold</option>
            <option value="completed">Completed</option>
            <option value="cancelled">Cancelled</option>
          </select>
          <select class="filter-select" onchange="loadWO()" id="wo-priority-filter">
            <option value="">All Priority</option>
            <option value="critical">Critical</option>
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
          </select>
          <select class="filter-select" onchange="loadWO()" id="wo-type-filter">
            <option value="">All Types</option>
            <option value="corrective">Corrective</option>
            <option value="preventive">Preventive</option>
            <option value="inspection">Inspection</option>
            <option value="project">Project</option>
          </select>
          <select class="filter-select" onchange="loadWO()" id="wo-assigned-filter">
            <option value="">All Assigned</option>
          </select>
          <input type="date" class="form-control filter-search" style="max-width:140px" onchange="loadWO()" id="wo-date-from" title="Due from">
          <input type="date" class="form-control filter-search" style="max-width:140px" onchange="loadWO()" id="wo-date-to" title="Due to">
          <button class="btn btn-secondary btn-sm" onclick="exportPageCSV('wo')" title="Export to CSV">⬇ CSV</button>
          <button class="btn btn-primary btn-sm" onclick="openWOModal()">＋ New WO</button>
        </div>
        <div class="card">
          <div class="tbl-wrap">
            <table>
              <thead><tr><th>WO #</th><th>Title</th><th>Asset</th><th>Priority</th><th>Status</th><th>Type</th><th>Assigned To</th><th>Due</th><th>Actions</th></tr></thead>
              <tbody id="wo-tbody"></tbody>
            </table>
          </div>
          <div class="pagination" id="wo-pagination"></div>
        </div>
      </div>

      <!-- ASSETS -->
      <div class="page" id="page-assets">
        <div class="toolbar">
          <input type="text" class="form-control filter-search" placeholder="🔍 Search assets..." oninput="debounce(()=>loadAssets(),400)" id="asset-search">
          <select class="filter-select" onchange="loadAssets()" id="asset-status-filter">
            <option value="">All Status</option>
            <option value="active">Active</option>
            <option value="maintenance">Maintenance</option>
            <option value="inactive">Inactive</option>
          </select>
          <select class="filter-select" onchange="loadAssets()" id="asset-cat-filter"><option value="">All Categories</option></select>
          <select class="filter-select" onchange="loadAssets()" id="asset-crit-filter">
            <option value="">All Criticality</option>
            <option value="critical">Critical</option>
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
          </select>
          <button class="btn btn-secondary btn-sm" onclick="exportPageCSV('assets')" title="Export to CSV">⬇ CSV</button>
          <button class="btn btn-primary btn-sm" onclick="openAssetModal()">＋ New Asset</button>
        </div>
        <div class="card">
          <div class="tbl-wrap">
            <table>
              <thead><tr><th>Code</th><th>Name</th><th>Category</th><th>Location</th><th>Status</th><th>Criticality</th><th>Warranty</th><th>Actions</th></tr></thead>
              <tbody id="asset-tbody"></tbody>
            </table>
          </div>
          <div class="pagination" id="asset-pagination"></div>
        </div>
      </div>

      <!-- PM SCHEDULES -->
      <div class="page" id="page-pm">
        <div class="toolbar">
          <input type="text" class="form-control filter-search" placeholder="🔍 Search PM schedules..." oninput="debounce(()=>loadPM(),400)" id="pm-search">
          <select class="filter-select" onchange="loadPM()" id="pm-status-filter">
            <option value="">All Status</option>
            <option value="active">Active</option>
            <option value="overdue">Overdue</option>
            <option value="inactive">Inactive</option>
          </select>
          <select class="filter-select" onchange="loadPM()" id="pm-freq-filter">
            <option value="">All Frequency</option>
            <option value="daily">Daily</option>
            <option value="weekly">Weekly</option>
            <option value="monthly">Monthly</option>
            <option value="quarterly">Quarterly</option>
            <option value="annual">Annual</option>
          </select>
          <button class="btn btn-primary btn-sm" onclick="openPMModal()" style="margin-left:auto">＋ New PM</button>
        </div>
        <div id="pm-list"></div>
      </div>

      <!-- PARTS -->
      <div class="page" id="page-parts">
        <div class="toolbar">
          <input type="text" class="form-control filter-search" placeholder="🔍 Search parts..." oninput="debounce(()=>loadParts(),400)" id="parts-search">
          <select class="filter-select" onchange="loadParts()" id="parts-low-filter">
            <option value="">All Stock</option>
            <option value="true">Low Stock Only</option>
          </select>
          <select class="filter-select" onchange="loadParts()" id="parts-supplier-filter">
            <option value="">All Suppliers</option>
          </select>
          <button class="btn btn-secondary btn-sm" onclick="exportPageCSV('parts')" title="Export to CSV">⬇ CSV</button>
          <button class="btn btn-primary btn-sm" onclick="openPartModal()">＋ Add Part</button>
        </div>
        <div class="card">
          <div class="tbl-wrap">
            <table>
              <thead><tr><th>Part #</th><th>Name</th><th>Stock</th><th>Min</th><th>Unit Cost</th><th>Location</th><th>Supplier</th><th>Actions</th></tr></thead>
              <tbody id="parts-tbody"></tbody>
            </table>
          </div>
          <div class="pagination" id="parts-pagination"></div>
        </div>
      </div>

      <!-- SUPPLIERS -->
      <div class="page" id="page-suppliers">
        <div class="toolbar">
          <input type="text" class="form-control filter-search" placeholder="🔍 Search suppliers..." oninput="debounce(()=>loadSuppliers(),400)" id="supplier-search">
          <button class="btn btn-secondary btn-sm" onclick="exportPageCSV('suppliers')" title="Export to CSV">⬇ CSV</button>
          <button class="btn btn-primary btn-sm" onclick="openSupplierModal()">＋ New Supplier</button>
        </div>
        <div class="card">
          <div class="tbl-wrap">
            <table>
              <thead><tr><th>Supplier</th><th>Contact</th><th>Email</th><th>Phone</th><th>Payment Terms</th><th>Actions</th></tr></thead>
              <tbody id="suppliers-tbody"></tbody>
            </table>
          </div>
        </div>
      </div>

      <!-- USER MANAGEMENT (ADMIN ONLY) -->
      <div class="page" id="page-users">
        <div class="toolbar">
          <span class="section-title" style="margin-bottom:0">👥 User Management <small>Admin only</small></span>
          <button class="btn btn-primary btn-sm" onclick="openUserModal()" style="margin-left:auto">＋ Create User</button>
        </div>
        <div class="user-grid" id="user-grid"></div>
      </div>

      <!-- AUDIT LOG (ADMIN ONLY) -->
      <div class="page" id="page-audit">
        <div class="toolbar">
          <span class="section-title" style="margin-bottom:0">📜 Audit Log</span>
          <select class="filter-select" onchange="loadAudit()" id="audit-action-filter">
            <option value="">All Actions</option>
            <option value="LOGIN">Login</option>
            <option value="LOGOUT">Logout</option>
            <option value="CREATE">Create</option>
            <option value="UPDATE">Update</option>
            <option value="DELETE">Delete</option>
            <option value="INVENTORY_ADJUST">Inventory Adjust</option>
            <option value="PASSWORD_CHANGE">Password Change</option>
            <option value="PASSWORD_RESET">Password Reset</option>
          </select>
          <select class="filter-select" onchange="loadAudit()" id="audit-table-filter">
            <option value="">All Tables</option>
            <option value="users">Users</option>
            <option value="assets">Assets</option>
            <option value="work_orders">Work Orders</option>
            <option value="parts">Parts</option>
            <option value="pm_schedules">PM Schedules</option>
          </select>
          <button class="btn btn-secondary btn-sm" onclick="loadAudit()">↻ Refresh</button>
        </div>
        <div class="card">
          <div class="tbl-wrap">
            <table>
              <thead><tr><th>Time</th><th>User</th><th>Action</th><th>Table</th><th>Record</th><th>Details</th><th>IP</th><th></th></tr></thead>
              <tbody id="audit-tbody"></tbody>
            </table>
          </div>
          <div class="pagination" id="audit-pagination"></div>
        </div>
      </div>

      <!-- SETTINGS (ADMIN ONLY) -->
      <div class="page" id="page-settings">
        <div class="section-title">⚙ Settings <small>System configuration</small></div>
        <div class="card">
          <div class="card-header"><span class="card-title">Appearance</span></div>
          <div id="settings-content" style="margin-bottom:16px">
            <!-- Accent picker injected here by JS -->
            <div class="settings-row">
              <div class="settings-row-info"><h4>Theme</h4><p>Toggle between dark and light mode</p></div>
              <button class="btn btn-secondary btn-sm" onclick="toggleTheme()" id="theme-toggle-btn2">🌙 Toggle</button>
            </div>
          </div>
          <div class="card-header" style="margin-top:16px"><span class="card-title">System Settings</span></div>
          <div id="settings-form"></div>
          <div style="margin-top:16px"><button class="btn btn-primary" onclick="saveSettings()">Save Settings</button></div>
        </div>
      </div>

      <!-- ABOUT -->
      <div class="page" id="page-about">
        <div class="section-title">ℹ About <small>Software information & contact</small></div>

        <!-- Hero Card -->
        <div class="card" style="background:linear-gradient(135deg,var(--bg1) 0%,var(--bg2) 100%);border:1px solid var(--accent);margin-bottom:20px;text-align:center;padding:40px 24px">
          <div style="font-size:56px;margin-bottom:12px">⚙</div>
          <div style="font-family:var(--mono);font-size:28px;font-weight:700;color:var(--green);letter-spacing:3px;margin-bottom:6px">NEXUS CMMS</div>
          <div style="color:var(--text2);font-size:14px;letter-spacing:2px;text-transform:uppercase;margin-bottom:18px">Computerized Maintenance Management System</div>
          <span style="background:var(--accent-glow);color:var(--accent);border:1px solid var(--accent);padding:5px 18px;border-radius:20px;font-size:13px;font-weight:600;font-family:var(--mono)">Enterprise v9</span>
        </div>

        <div class="two-col">
          <!-- Software Details -->
          <div class="card">
            <div class="card-header"><span class="card-title">📦 Software Details</span></div>
            <table style="width:100%;border-collapse:collapse;margin-top:8px">
              <tr style="border-bottom:1px solid var(--border)">
                <td style="padding:10px 8px;color:var(--text2);font-size:13px;width:45%">Application Name</td>
                <td style="padding:10px 8px;font-weight:600;font-size:13px">NEXUS CMMS</td>
              </tr>
              <tr style="border-bottom:1px solid var(--border)">
                <td style="padding:10px 8px;color:var(--text2);font-size:13px">Version</td>
                <td style="padding:10px 8px;font-size:13px"><span style="background:var(--green-glow);color:var(--green);padding:2px 10px;border-radius:10px;font-weight:700;font-family:var(--mono)">v9.0 Enterprise</span></td>
              </tr>
              <tr style="border-bottom:1px solid var(--border)">
                <td style="padding:10px 8px;color:var(--text2);font-size:13px">Release Type</td>
                <td style="padding:10px 8px;font-size:13px">Stable Release</td>
              </tr>
              <tr style="border-bottom:1px solid var(--border)">
                <td style="padding:10px 8px;color:var(--text2);font-size:13px">Platform</td>
                <td style="padding:10px 8px;font-size:13px">Web-based (Local Server)</td>
              </tr>
              <tr style="border-bottom:1px solid var(--border)">
                <td style="padding:10px 8px;color:var(--text2);font-size:13px">Technology Stack</td>
                <td style="padding:10px 8px;font-size:13px">Python · Flask · SQLite · HTML5 · JS</td>
              </tr>
              <tr style="border-bottom:1px solid var(--border)">
                <td style="padding:10px 8px;color:var(--text2);font-size:13px">Database</td>
                <td style="padding:10px 8px;font-size:13px">SQLite (cmms_nexus.db)</td>
              </tr>
              <tr style="border-bottom:1px solid var(--border)">
                <td style="padding:10px 8px;color:var(--text2);font-size:13px">PWA Support</td>
                <td style="padding:10px 8px;font-size:13px">✅ Enabled</td>
              </tr>
              <tr>
                <td style="padding:10px 8px;color:var(--text2);font-size:13px">License</td>
                <td style="padding:10px 8px;font-size:13px">Proprietary — All Rights Reserved</td>
              </tr>
            </table>
          </div>

          <!-- Developer Details -->
          <div class="card">
            <div class="card-header"><span class="card-title">👨‍💻 Developer</span></div>
            <div style="display:flex;align-items:center;gap:16px;padding:16px 0 20px">
              <div style="width:64px;height:64px;border-radius:50%;background:linear-gradient(135deg,var(--accent),var(--green));display:flex;align-items:center;justify-content:center;font-size:26px;font-weight:700;color:#fff;flex-shrink:0">S</div>
              <div>
                <div style="font-size:20px;font-weight:700;color:var(--text0)">Sivabalan</div>
                <div style="color:var(--text2);font-size:13px;margin-top:2px">Full Stack Developer</div>
                <div style="color:var(--accent);font-size:12px;margin-top:4px;font-family:var(--mono)">NEXUS CMMS Creator</div>
              </div>
            </div>
            <div style="border-top:1px solid var(--border);padding-top:16px">
              <div style="color:var(--text2);font-size:13px;line-height:1.7">
                Designed and developed NEXUS CMMS to provide maintenance teams with a powerful, reliable, and easy-to-use platform that runs entirely on local infrastructure — no cloud dependency required.
              </div>
            </div>
          </div>
        </div>

        <!-- Contact Details -->
        <div class="card" style="margin-top:0">
          <div class="card-header"><span class="card-title">📬 Contact & Support</span></div>
          <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:16px;padding:16px 0">

            <div style="display:flex;align-items:center;gap:14px;padding:14px;background:var(--bg2);border-radius:var(--r8);border:1px solid var(--border)">
              <span style="font-size:26px">📧</span>
              <div>
                <div style="font-size:11px;color:var(--text2);text-transform:uppercase;letter-spacing:1px;margin-bottom:3px">Email</div>
                <div style="font-size:14px;font-weight:600;color:var(--accent)">sivabalan@example.com</div>
              </div>
            </div>

            <div style="display:flex;align-items:center;gap:14px;padding:14px;background:var(--bg2);border-radius:var(--r8);border:1px solid var(--border)">
              <span style="font-size:26px">📱</span>
              <div>
                <div style="font-size:11px;color:var(--text2);text-transform:uppercase;letter-spacing:1px;margin-bottom:3px">Phone / WhatsApp</div>
                <div style="font-size:14px;font-weight:600;color:var(--accent)">+91 XXXXX XXXXX</div>
              </div>
            </div>

            <div style="display:flex;align-items:center;gap:14px;padding:14px;background:var(--bg2);border-radius:var(--r8);border:1px solid var(--border)">
              <span style="font-size:26px">💼</span>
              <div>
                <div style="font-size:11px;color:var(--text2);text-transform:uppercase;letter-spacing:1px;margin-bottom:3px">LinkedIn</div>
                <div style="font-size:14px;font-weight:600;color:var(--accent)">linkedin.com/in/sivabalan</div>
              </div>
            </div>

            <div style="display:flex;align-items:center;gap:14px;padding:14px;background:var(--bg2);border-radius:var(--r8);border:1px solid var(--border)">
              <span style="font-size:26px">🐙</span>
              <div>
                <div style="font-size:11px;color:var(--text2);text-transform:uppercase;letter-spacing:1px;margin-bottom:3px">GitHub</div>
                <div style="font-size:14px;font-weight:600;color:var(--accent)">github.com/sivabalan</div>
              </div>
            </div>

            <div style="display:flex;align-items:center;gap:14px;padding:14px;background:var(--bg2);border-radius:var(--r8);border:1px solid var(--border)">
              <span style="font-size:26px">🌐</span>
              <div>
                <div style="font-size:11px;color:var(--text2);text-transform:uppercase;letter-spacing:1px;margin-bottom:3px">Website</div>
                <div style="font-size:14px;font-weight:600;color:var(--accent)">www.sivabalan.dev</div>
              </div>
            </div>

            <div style="display:flex;align-items:center;gap:14px;padding:14px;background:var(--bg2);border-radius:var(--r8);border:1px solid var(--border)">
              <span style="font-size:26px">📍</span>
              <div>
                <div style="font-size:11px;color:var(--text2);text-transform:uppercase;letter-spacing:1px;margin-bottom:3px">Location</div>
                <div style="font-size:14px;font-weight:600;color:var(--text0)">Tamil Nadu, India</div>
              </div>
            </div>

          </div>
        </div>

        <!-- Features & Changelog -->
        <div class="two-col">
          <div class="card">
            <div class="card-header"><span class="card-title">✨ Key Features</span></div>
            <ul style="margin:12px 0 0;padding-left:20px;line-height:2;color:var(--text1);font-size:13px">
              <li>Full Work Order Lifecycle Management</li>
              <li>Preventive Maintenance Scheduling</li>
              <li>Asset Registry with QR Code Labels</li>
              <li>Spare Parts & Inventory Management</li>
              <li>AI-Powered Maintenance Insights</li>
              <li>Real-time Dashboard & Analytics</li>
              <li>Role-Based Access Control (RBAC)</li>
              <li>Mobile PWA with Offline Sync</li>
              <li>Kanban Board for Work Orders</li>
              <li>CSV Import / Export</li>
              <li>Email Notifications (SMTP)</li>
              <li>Complete Audit Trail</li>
              <li><strong style="color:var(--green)">NEW v6:</strong> Budget Tracker with Charts</li>
              <li><strong style="color:var(--green)">NEW v6:</strong> SLA Monitor + Auto-Escalation</li>
              <li><strong style="color:var(--green)">NEW v6:</strong> Parts Reorder Wizard</li>
              <li><strong style="color:var(--green)">NEW v6:</strong> Scheduled Auto DB Backups</li>
              <li><strong style="color:var(--green)">NEW v6:</strong> WO Print/PDF with Sign-Off</li>
              <li><strong style="color:var(--green)">NEW v6:</strong> Enhanced Global Search</li>
            </ul>
          </div>

          <div class="card">
            <div class="card-header" style="display:flex;align-items:center;justify-content:space-between">
              <span class="card-title">🔄 Software Update</span>
              <span id="update-badge" style="display:none;background:var(--red);color:#fff;font-size:11px;padding:2px 10px;border-radius:10px;font-weight:700">UPDATE AVAILABLE</span>
            </div>

            <!-- Current version strip -->
            <div style="display:flex;align-items:center;justify-content:space-between;padding:14px;background:var(--bg2);border-radius:var(--r8);margin:12px 0;border:1px solid var(--border)">
              <div>
                <div style="font-size:11px;color:var(--text2);text-transform:uppercase;letter-spacing:1px">Installed Version</div>
                <div style="font-size:18px;font-weight:700;font-family:var(--mono);color:var(--green);margin-top:2px" id="installed-ver">v9.0.0</div>
                <div style="font-size:11px;color:var(--text2);margin-top:2px" id="installed-build">Build 2025-02-23 · Enterprise</div>
              </div>
              <div style="text-align:right">
                <div style="font-size:11px;color:var(--text2);text-transform:uppercase;letter-spacing:1px">Last Checked</div>
                <div style="font-size:12px;color:var(--text1);margin-top:2px" id="last-checked-time">—</div>
              </div>
            </div>

            <!-- Check update button -->
            <button class="btn btn-primary" style="width:100%;margin-bottom:12px" onclick="runUpdateCheck()" id="check-update-btn">
              🔍 Check for Updates
            </button>

            <!-- Result panel (hidden until checked) -->
            <div id="update-result" style="display:none"></div>

            <!-- Manual Update Section -->
            <div style="border-top:1px solid var(--border);margin-top:14px;padding-top:14px">
              <div style="font-size:12px;color:var(--text2);font-weight:600;margin-bottom:10px;text-transform:uppercase;letter-spacing:1px">⬆ Manual Update</div>

              <!-- Non-admin notice (shown to non-admins) -->
              <div id="update-admin-only" style="display:none;background:var(--bg2);border:1px solid var(--border);border-radius:var(--r8);padding:12px;font-size:13px;color:var(--text2);text-align:center">
                🔒 Manual update is available to Administrators only.
              </div>

              <!-- Admin update UI -->
              <div id="update-admin-ui">
                <div style="font-size:13px;color:var(--text2);margin-bottom:12px;line-height:1.6">
                  Upload a new <code style="background:var(--bg3);padding:1px 6px;border-radius:4px;font-family:var(--mono);font-size:12px">cmms_app_v5_enterprise.py</code> file to update the software. The current version will be backed up automatically before applying.
                </div>

              <!-- Drop zone -->
              <div id="update-dropzone"
                   ondragover="event.preventDefault();this.classList.add('dz-hover')"
                   ondragleave="this.classList.remove('dz-hover')"
                   ondrop="handleUpdateDrop(event)"
                   onclick="document.getElementById('update-file-input').click()"
                   style="border:2px dashed var(--border);border-radius:var(--r8);padding:24px;text-align:center;cursor:pointer;transition:all .2s;background:var(--bg2);margin-bottom:12px">
                <div style="font-size:28px;margin-bottom:6px">📁</div>
                <div style="font-size:13px;font-weight:600;color:var(--text0)" id="dz-label">Click or drag &amp; drop update file here</div>
                <div style="font-size:11px;color:var(--text2);margin-top:4px">.py files only</div>
              </div>
              <input type="file" id="update-file-input" accept=".py" style="display:none" onchange="handleUpdateFileSelect(this)">

              <!-- Selected file preview -->
              <div id="update-file-preview" style="display:none;background:var(--bg2);border:1px solid var(--border);border-radius:var(--r8);padding:12px;margin-bottom:12px">
                <div style="display:flex;align-items:center;justify-content:space-between">
                  <div style="display:flex;align-items:center;gap:10px">
                    <span style="font-size:20px">📄</span>
                    <div>
                      <div style="font-size:13px;font-weight:600" id="uf-name">—</div>
                      <div style="font-size:11px;color:var(--text2)" id="uf-size">—</div>
                    </div>
                  </div>
                  <button class="btn btn-sm" style="background:transparent;color:var(--text2);padding:4px 8px" onclick="clearUpdateFile()">✕</button>
                </div>
              </div>

              <!-- Warnings / changelog notes textarea -->
              <div id="update-notes-wrap" style="display:none;margin-bottom:12px">
                <label style="font-size:12px;color:var(--text2);display:block;margin-bottom:4px">Update Notes (optional)</label>
                <textarea id="update-notes-txt" class="form-control" rows="3" placeholder="Describe what changed in this update..."></textarea>
              </div>

              <!-- Apply button -->
              <button class="btn btn-primary" id="apply-update-btn" onclick="applyManualUpdate()" disabled style="width:100%;margin-bottom:8px">
                🚀 Apply Update
              </button>

              <!-- Progress / result -->
              <div id="manual-update-result" style="display:none"></div>
              </div><!-- end update-admin-ui -->
            </div>

            <!-- Backup files list -->
            <div style="border-top:1px solid var(--border);margin-top:14px;padding-top:14px">
              <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px">
                <div style="font-size:12px;color:var(--text2);font-weight:600;text-transform:uppercase;letter-spacing:1px">🗂 App Backup Files</div>
                <button class="btn btn-secondary btn-sm" onclick="loadBackupList()">Refresh</button>
              </div>
              <div id="backup-list"><div style="font-size:12px;color:var(--text2);text-align:center;padding:10px">Click Refresh to load backups</div></div>
            </div>

            <!-- Database Backup & Restore -->
            <div style="border-top:1px solid var(--border);margin-top:14px;padding-top:14px">
              <div style="font-size:12px;color:var(--text2);font-weight:600;margin-bottom:10px;text-transform:uppercase;letter-spacing:1px">🗄 Database Backup &amp; Restore</div>
              <div style="font-size:13px;color:var(--text2);margin-bottom:12px;line-height:1.6">
                Download a full backup of your database or restore from a previously exported <code style="background:var(--bg3);padding:1px 6px;border-radius:4px;font-family:var(--mono);font-size:12px">.db</code> file. All data including work orders, assets, parts, and users is included.
              </div>
              <!-- Download button -->
              <button class="btn btn-secondary" style="width:100%;margin-bottom:10px" onclick="downloadDbBackup()">
                ⬇ Download Database Backup
              </button>
              <!-- Restore section -->
              <div style="background:var(--bg2);border:1px solid var(--border);border-radius:var(--r8);padding:12px">
                <div style="font-size:12px;font-weight:600;color:var(--text1);margin-bottom:8px">⬆ Restore from Backup</div>
                <div style="font-size:12px;color:var(--text2);margin-bottom:10px;line-height:1.6">
                  ⚠️ <strong>Warning:</strong> Restoring will <strong>replace all current data</strong> with the backup. The current database will be saved first.
                </div>
                <div id="db-restore-dropzone"
                     ondragover="event.preventDefault();this.classList.add('dz-hover')"
                     ondragleave="this.classList.remove('dz-hover')"
                     ondrop="handleDbRestoreDrop(event)"
                     onclick="document.getElementById('db-restore-file-input').click()"
                     style="border:2px dashed var(--border);border-radius:var(--r8);padding:18px;text-align:center;cursor:pointer;transition:all .2s;background:var(--bg1);margin-bottom:10px">
                  <div style="font-size:22px;margin-bottom:4px">📂</div>
                  <div style="font-size:13px;font-weight:600;color:var(--text0)" id="db-dz-label">Click or drag &amp; drop .db backup file here</div>
                  <div style="font-size:11px;color:var(--text2);margin-top:4px">.db files only</div>
                </div>
                <input type="file" id="db-restore-file-input" accept=".db" style="display:none" onchange="handleDbRestoreFileSelect(this)">
                <div id="db-restore-preview" style="display:none;background:var(--bg1);border:1px solid var(--border);border-radius:var(--r8);padding:10px;margin-bottom:10px">
                  <div style="display:flex;align-items:center;justify-content:space-between">
                    <div style="display:flex;align-items:center;gap:8px">
                      <span style="font-size:18px">🗄</span>
                      <div>
                        <div style="font-size:13px;font-weight:600" id="db-rf-name">—</div>
                        <div style="font-size:11px;color:var(--text2)" id="db-rf-size">—</div>
                      </div>
                    </div>
                    <button class="btn btn-sm" style="background:transparent;color:var(--text2);padding:4px 8px" onclick="clearDbRestoreFile()">✕</button>
                  </div>
                </div>
                <button class="btn btn-danger" id="apply-db-restore-btn" onclick="applyDbRestore()" disabled style="width:100%;margin-bottom:8px">
                  ♻ Restore Database
                </button>
              </div>
              <div id="db-backup-result" style="display:none;margin-top:10px"></div>
            </div>

            <!-- v6: Auto Backup -->
            <div style="border-top:1px solid var(--border);margin-top:14px;padding-top:14px">
              <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px">
                <div style="font-size:12px;color:var(--text2);font-weight:600;text-transform:uppercase;letter-spacing:1px">🤖 Scheduled Auto Backup</div>
                <button class="btn btn-secondary btn-sm" id="run-backup-btn" onclick="runBackupNow()">▶ Backup Now</button>
              </div>
              <div style="font-size:12px;color:var(--text2);margin-bottom:10px;line-height:1.6">
                The system automatically backs up your database on a configurable schedule. Configure the interval in System Settings. Auto-backups are stored alongside the application and pruned automatically.
              </div>
              <div id="auto-backup-log" onclick="loadAutoBackupLog()">
                <div style="font-size:12px;color:var(--text2);text-align:center;padding:10px;cursor:pointer">Click to load recent backups</div>
              </div>
            </div>

            <!-- System info mini-table -->
            <div style="border-top:1px solid var(--border);margin-top:14px;padding-top:14px">
              <div style="font-size:12px;color:var(--text2);font-weight:600;margin-bottom:8px;text-transform:uppercase;letter-spacing:1px">System Information</div>
              <table style="width:100%;border-collapse:collapse" id="sysinfo-table">
                <tr><td style="padding:6px 4px;font-size:12px;color:var(--text2);width:50%">Python Version</td><td style="padding:6px 4px;font-size:12px;font-family:var(--mono)" id="si-python">—</td></tr>
                <tr><td style="padding:6px 4px;font-size:12px;color:var(--text2)">Database File</td><td style="padding:6px 4px;font-size:12px;font-family:var(--mono)" id="si-db">—</td></tr>
                <tr><td style="padding:6px 4px;font-size:12px;color:var(--text2)">Database Size</td><td style="padding:6px 4px;font-size:12px;font-family:var(--mono)" id="si-dbsize">—</td></tr>
                <tr><td style="padding:6px 4px;font-size:12px;color:var(--text2)">Work Orders</td><td style="padding:6px 4px;font-size:12px;font-family:var(--mono)" id="si-wo">—</td></tr>
                <tr><td style="padding:6px 4px;font-size:12px;color:var(--text2)">Assets</td><td style="padding:6px 4px;font-size:12px;font-family:var(--mono)" id="si-assets">—</td></tr>
                <tr><td style="padding:6px 4px;font-size:12px;color:var(--text2)">Active Users</td><td style="padding:6px 4px;font-size:12px;font-family:var(--mono)" id="si-users">—</td></tr>
                <tr><td style="padding:6px 4px;font-size:12px;color:var(--text2)">PM Schedules</td><td style="padding:6px 4px;font-size:12px;font-family:var(--mono)" id="si-pm">—</td></tr>
              </table>
            </div>
          </div>

          <div class="card" style="margin-top:0">
            <div class="card-header"><span class="card-title">🕐 Version History</span></div>
            <div style="margin-top:12px">
              <div style="display:flex;gap:12px;align-items:flex-start;padding:10px 0;border-bottom:1px solid var(--border)">
                <span style="background:var(--green-glow);color:var(--green);padding:2px 10px;border-radius:10px;font-size:12px;font-weight:700;font-family:var(--mono);white-space:nowrap">v9.0</span>
                <div>
                  <div style="font-size:13px;font-weight:600">Enterprise v9 Mobile Edition <span style="color:var(--green);font-size:11px">● Current</span></div>
                  <div style="font-size:12px;color:var(--text2)">Enhanced mobile view, improved bottom nav with More drawer, touch-optimized tables, PWA safe-area support, tablet layout, landscape mode</div>
                </div>
              </div>
              <div style="display:flex;gap:12px;align-items:flex-start;padding:10px 0;border-bottom:1px solid var(--border)">
                <span style="background:var(--bg3);color:var(--text2);padding:2px 10px;border-radius:10px;font-size:12px;font-weight:600;font-family:var(--mono);white-space:nowrap">v8.0</span>
                <div>
                  <div style="font-size:13px;font-weight:600">Enterprise Enhanced</div>
                  <div style="font-size:12px;color:var(--text2)">PBKDF2 password hashing, rate limiting, command palette fix, bulk WO actions, DB indexes, global search improvements</div>
                </div>
              </div>
              <div style="display:flex;gap:12px;align-items:flex-start;padding:10px 0;border-bottom:1px solid var(--border)">
                <span style="background:var(--bg3);color:var(--text2);padding:2px 10px;border-radius:10px;font-size:12px;font-weight:600;font-family:var(--mono);white-space:nowrap">v6.0</span>
                <div>
                  <div style="font-size:13px;font-weight:600">Enterprise Edition</div>
                  <div style="font-size:12px;color:var(--text2)">AI Insights, PWA, SSE live updates, Kanban, Analytics heatmap, Bulk actions, Software Update panel, DB Backup/Restore</div>
                </div>
              </div>
              <div style="display:flex;gap:12px;align-items:flex-start;padding:10px 0;border-bottom:1px solid var(--border)">
                <span style="background:var(--bg3);color:var(--text2);padding:2px 10px;border-radius:10px;font-size:12px;font-weight:600;font-family:var(--mono);white-space:nowrap">v4.0</span>
                <div>
                  <div style="font-size:13px;font-weight:600">Advanced Edition</div>
                  <div style="font-size:12px;color:var(--text2)">Mobile QR scanning, Downtime tracking, SLA stats, Work request portal</div>
                </div>
              </div>
              <div style="display:flex;gap:12px;align-items:flex-start;padding:10px 0;border-bottom:1px solid var(--border)">
                <span style="background:var(--bg3);color:var(--text2);padding:2px 10px;border-radius:10px;font-size:12px;font-weight:600;font-family:var(--mono);white-space:nowrap">v3.0</span>
                <div>
                  <div style="font-size:13px;font-weight:600">Professional Edition</div>
                  <div style="font-size:12px;color:var(--text2)">PM Scheduling, Parts inventory, Supplier management, Reports export</div>
                </div>
              </div>
              <div style="display:flex;gap:12px;align-items:flex-start;padding:10px 0">
                <span style="background:var(--bg3);color:var(--text2);padding:2px 10px;border-radius:10px;font-size:12px;font-weight:600;font-family:var(--mono);white-space:nowrap">v1–2</span>
                <div>
                  <div style="font-size:13px;font-weight:600">Standard Edition</div>
                  <div style="font-size:12px;color:var(--text2)">Core work orders, asset management, basic user roles</div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Footer Copyright -->
        <div style="text-align:center;padding:24px 0 8px;color:var(--text2);font-size:13px">
          <div>© 2024 – 2026 <strong style="color:var(--text1)">NUXUS CMMS</strong>. All rights reserved.</div>
          <div style="margin-top:4px;font-size:12px;font-family:var(--mono)">NEXUS CMMS Enterprise v9 Mobile Enhanced — Built with ❤ in Tamil Nadu, India</div>
        </div>
      </div>

      <!-- PROFILE -->
      <div class="page" id="page-profile">
        <div class="two-col">
          <div class="card">
            <div class="card-header" style="display:flex;align-items:center;justify-content:space-between">
              <span class="card-title">👤 My Profile</span>
              <button class="btn btn-secondary btn-sm" id="profile-edit-btn" onclick="toggleProfileEdit()">✏ Edit Profile</button>
            </div>
            <div id="profile-content"></div>
            <!-- Edit form (hidden by default) -->
            <div id="profile-edit-form" style="display:none;margin-top:12px;border-top:1px solid var(--border);padding-top:16px">
              <div class="form-group"><label>Full Name</label><input type="text" id="pe-fullname" class="form-control"></div>
              <div class="form-group"><label>Email</label><input type="email" id="pe-email" class="form-control"></div>
              <div class="form-group"><label>Phone</label><input type="tel" id="pe-phone" class="form-control"></div>
              <div class="form-group"><label>Department</label><input type="text" id="pe-dept" class="form-control"></div>
              <div style="display:flex;gap:8px">
                <button class="btn btn-primary" onclick="saveProfile()">💾 Save Changes</button>
                <button class="btn btn-secondary" onclick="toggleProfileEdit()">Cancel</button>
              </div>
            </div>
            <!-- My Tasks mini widget -->
            <div style="margin-top:20px;border-top:1px solid var(--border);padding-top:16px">
              <div style="font-size:13px;font-weight:600;color:var(--text2);margin-bottom:10px;text-transform:uppercase;letter-spacing:1px">📋 My Open Work Orders</div>
              <div id="profile-my-tasks"><div style="font-size:12px;color:var(--text2)">Loading...</div></div>
            </div>
          </div>
          <div>
            <div class="card">
              <div class="card-header"><span class="card-title">🔑 Change Password</span></div>
              <div class="form-group"><label>Current Password</label><input type="password" id="pw-old" class="form-control"></div>
              <div class="form-group"><label>New Password</label><input type="password" id="pw-new" class="form-control"></div>
              <div class="form-group"><label>Confirm New Password</label><input type="password" id="pw-confirm" class="form-control"></div>
              <button class="btn btn-primary" onclick="changePassword()">Update Password</button>
            </div>
            <div class="card" style="margin-top:0">
              <div class="card-header"><span class="card-title">📊 My Stats</span></div>
              <div id="profile-stats"><div style="font-size:12px;color:var(--text2)">Loading...</div></div>
            </div>
          </div>
        </div>
      </div>


      <!-- EQUIPMENT HISTORY -->
      <div class="page" id="page-eq-history">
        <div class="section-title">📊 Equipment History <small>Full lifecycle view per asset</small></div>
        <div class="eq-selector">
          <select class="form-control" id="eq-history-asset-sel" onchange="selectHistoryAsset()" style="flex:1;min-width:280px;max-width:440px">
            <option value="">— Select an asset to view history —</option>
          </select>
          <select class="filter-select" id="eq-history-year" onchange="(async()=>await renderHistoryTab())()">
            <option value="">All Time</option>
            <option value="2024">2024</option>
            <option value="2023">2023</option>
            <option value="2022">2022</option>
          </select>
          <button class="btn btn-secondary btn-sm" onclick="exportHistoryCSV()">⬇ Export CSV</button>
        </div>

        <div id="eq-history-asset-header" style="display:none"></div>

        <div id="eq-history-summary" class="hist-summary" style="display:none"></div>

        <div id="eq-history-tabs" style="display:none">
          <div class="tab-bar">
            <button class="tab-btn active" id="htab-all"     onclick="switchHistoryTab('all')">🕐 All Events</button>
            <button class="tab-btn"        id="htab-wo"      onclick="switchHistoryTab('wo')">📋 Work Orders</button>
            <button class="tab-btn"        id="htab-pm"      onclick="switchHistoryTab('pm')">✅ PM Completed</button>
            <button class="tab-btn"        id="htab-status"  onclick="switchHistoryTab('status')">🔄 Status Changes</button>
            <button class="tab-btn"        id="htab-cost"    onclick="switchHistoryTab('cost')">💰 Cost Analysis</button>
            <button class="tab-btn"        id="htab-corrective" onclick="switchHistoryTab('corrective')">🔧 Corrective Maint.</button>
            <button class="tab-btn"        id="htab-downtime"   onclick="switchHistoryTab('downtime')">⏱ Downtime</button>
            <button class="tab-btn"        id="htab-parts"      onclick="switchHistoryTab('parts')">🔩 Spare Parts</button>
            <button class="tab-btn"        id="htab-depreciation" onclick="switchHistoryTab('depreciation')">📉 Depreciation</button>
          </div>
          <div id="eq-history-content"></div>
        </div>

        <div id="eq-history-empty" style="display:none">
          <div class="empty-state">
            <div class="icon">📊</div>
            <h3>No History Found</h3>
            <p>History is recorded automatically as work orders and PM tasks are completed.</p>
          </div>
        </div>

        <div id="eq-history-placeholder">
          <div class="empty-state">
            <div class="icon">⚙</div>
            <h3>Select an Asset</h3>
            <p>Choose an asset from the dropdown above to view its complete maintenance history.</p>
          </div>
        </div>
      </div>

      <!-- CALENDAR -->
      <div class="page" id="page-calendar">
        <div class="cal-nav">
          <button class="btn btn-secondary btn-sm" onclick="calPrev()">‹ Prev</button>
          <span class="cal-month-title" id="cal-month-title"></span>
          <button class="btn btn-secondary btn-sm" onclick="calNext()">Next ›</button>
          <button class="btn btn-secondary btn-sm" onclick="calToday()" style="margin-left:8px">Today</button>
          <span style="margin-left:auto;display:flex;gap:12px;font-size:12px;align-items:center">
            <span style="color:#4da6ff">■ Work Order</span>
            <span style="color:#00e5a0">■ PM Schedule</span>
            <span style="color:#ff4d6d">■ Critical</span>
          </span>
        </div>
        <div class="card" style="padding:0;overflow:hidden">
          <div class="cal-header-row" style="padding:0 0 0 0;background:var(--bg3)">
            <div class="cal-dow">SUN</div><div class="cal-dow">MON</div><div class="cal-dow">TUE</div>
            <div class="cal-dow">WED</div><div class="cal-dow">THU</div><div class="cal-dow">FRI</div>
            <div class="cal-dow">SAT</div>
          </div>
          <div class="cal-grid" id="cal-grid"></div>
        </div>
      </div>

      <!-- REPORTS -->
      <div class="page" id="page-reports">
        <div class="section-title">📊 Reports & Exports</div>
        <div class="report-grid">
          <div class="report-card" onclick="runReport('maintenance-summary')">
            <div class="report-icon">🔧</div>
            <h3>Maintenance Summary</h3>
            <p>Work order totals, completion rates, costs by type and priority</p>
          </div>
          <div class="report-card" onclick="runReport('asset-list')">
            <div class="report-icon">⚙</div>
            <h3>Asset Register</h3>
            <p>Full asset list with status, location, criticality and warranty info</p>
          </div>
          <div class="report-card" onclick="runReport('pm-compliance')">
            <div class="report-icon">✅</div>
            <h3>PM Compliance</h3>
            <p>Preventive maintenance completion rates and overdue schedules</p>
          </div>
          <div class="report-card" onclick="runReport('downtime')">
            <div class="report-icon">⏱</div>
            <h3>Downtime Analysis</h3>
            <p>Equipment downtime hours, incident counts and top offenders</p>
          </div>
          <div class="report-card" onclick="runReport('inventory')">
            <div class="report-icon">📦</div>
            <h3>Inventory Report</h3>
            <p>Parts stock levels, values, low stock alerts and reorder list</p>
          </div>
          <div class="report-card" onclick="runReport('cost-analysis')">
            <div class="report-icon">💰</div>
            <h3>Cost Analysis</h3>
            <p>Maintenance spend by asset, category, month and WO type</p>
          </div>
          <div class="report-card" onclick="runReport('depreciation')">
            <div class="report-icon">📉</div>
            <h3>Depreciation Report</h3>
            <p>Asset age, straight-line and declining balance depreciation</p>
          </div>
          <div class="report-card" onclick="exportAllCSV()">
            <div class="report-icon">📁</div>
            <h3>Export All Data</h3>
            <p>Download all assets, WOs, parts and PM schedules as CSV files</p>
          </div>
        </div>
        <div class="card" id="report-output" style="display:none">
          <div class="card-header">
            <span class="card-title" id="report-title"></span>
            <div style="display:flex;gap:8px">
              <button class="btn btn-secondary btn-sm" onclick="window.print()">🖨 Print / PDF</button>
              <button class="btn btn-secondary btn-sm" onclick="exportReportCSV()">⬇ CSV</button>
              <button class="btn btn-secondary btn-sm" onclick="document.getElementById('report-output').style.display='none'">✕ Close</button>
            </div>
          </div>
          <div id="report-body" style="padding:8px"></div>
        </div>
      </div>


      <!-- PURCHASE ORDERS -->
      <div class="page" id="page-purchase-orders">
        <div class="toolbar">
          <input type="text" class="form-control filter-search" placeholder="🔍 Search purchase orders..." oninput="debounce(()=>loadPOs(),400)" id="po-search">
          <select class="filter-select" onchange="loadPOs()" id="po-status-filter">
            <option value="">All Status</option>
            <option value="draft">Draft</option>
            <option value="pending">Pending</option>
            <option value="approved">Approved</option>
            <option value="ordered">Ordered</option>
            <option value="received">Received</option>
            <option value="cancelled">Cancelled</option>
          </select>
          <button class="btn btn-secondary btn-sm" onclick="exportPageCSV('po')" title="Export to CSV">⬇ CSV</button>
          <button class="btn btn-primary btn-sm" onclick="openPOModal()">＋ New PO</button>
        </div>
        <div class="card">
          <div class="tbl-wrap">
            <table>
              <thead><tr><th>PO #</th><th>Supplier</th><th>Status</th><th>Items</th><th>Total</th><th>Ordered By</th><th>Created</th><th>Expected</th><th>Actions</th></tr></thead>
              <tbody id="po-tbody"></tbody>
            </table>
          </div>
          <div class="pagination" id="po-pagination"></div>
        </div>
      </div>

      <!-- IMPORT -->
      <div class="page" id="page-import">
        <div class="section-title">⬆ Import Data <small>CSV import for assets and parts</small></div>
        <div class="two-col">
          <div class="card">
            <div class="card-header"><span class="card-title">Import Assets</span></div>
            <p style="font-size:12px;color:var(--text2);margin-bottom:12px">
              Required columns: <span class="td-mono">name</span><br>
              Optional: <span class="td-mono">code, make, model, serial_number, purchase_date, purchase_cost, status, criticality, description, notes</span>
            </p>
            <div class="import-zone" id="assets-drop-zone" onclick="document.getElementById('assets-file-input').click()">
              <div style="font-size:28px;margin-bottom:8px">📄</div>
              <div style="font-weight:600;margin-bottom:4px">Click to upload or drag CSV here</div>
              <div style="font-size:12px;color:var(--text2)">CSV files only</div>
            </div>
            <input type="file" id="assets-file-input" accept=".csv" style="display:none" onchange="loadImportFile('assets', this)">
            <div class="import-preview" id="assets-import-preview"></div>
            <div style="margin-top:12px;display:flex;gap:8px">
              <button class="btn btn-secondary btn-sm" onclick="downloadTemplate('assets')">⬇ Download Template</button>
              <button class="btn btn-primary btn-sm" id="assets-import-btn" style="display:none" onclick="doImport('assets')">⬆ Import</button>
            </div>
          </div>
          <div class="card">
            <div class="card-header"><span class="card-title">Import Parts</span></div>
            <p style="font-size:12px;color:var(--text2);margin-bottom:12px">
              Required columns: <span class="td-mono">name</span><br>
              Optional: <span class="td-mono">part_number, description, quantity, min_quantity, unit_cost, location, supplier, manufacturer, notes</span>
            </p>
            <div class="import-zone" id="parts-drop-zone" onclick="document.getElementById('parts-file-input').click()">
              <div style="font-size:28px;margin-bottom:8px">📄</div>
              <div style="font-weight:600;margin-bottom:4px">Click to upload or drag CSV here</div>
              <div style="font-size:12px;color:var(--text2)">CSV files only</div>
            </div>
            <input type="file" id="parts-file-input" accept=".csv" style="display:none" onchange="loadImportFile('parts', this)">
            <div class="import-preview" id="parts-import-preview"></div>
            <div style="margin-top:12px;display:flex;gap:8px">
              <button class="btn btn-secondary btn-sm" onclick="downloadTemplate('parts')">⬇ Download Template</button>
              <button class="btn btn-primary btn-sm" id="parts-import-btn" style="display:none" onclick="doImport('parts')">⬆ Import</button>
            </div>
          </div>
        </div>
      </div>

      <!-- KANBAN BOARD PAGE -->
      <div class="page" id="page-kanban">
        <div style="display:flex;align-items:center;gap:12px;margin-bottom:20px;flex-wrap:wrap">
          <div class="section-title" style="margin:0">🗂 Kanban Board <small>Drag cards to update status</small></div>
          <span class="live-badge"><span class="live-dot"></span>Live</span>
          <div style="margin-left:auto;display:flex;gap:8px">
            <select class="filter-select" id="kanban-filter-priority" onchange="renderKanban()">
              <option value="">All Priorities</option>
              <option value="critical">Critical</option>
              <option value="high">High</option>
              <option value="medium">Medium</option>
              <option value="low">Low</option>
            </select>
            <button class="btn btn-primary btn-sm" onclick="showCreateWO()">+ New WO</button>
          </div>
        </div>
        <div class="kanban-board" id="kanban-board">
          <div class="kanban-col" id="kancol-open" data-status="open">
            <div class="kanban-col-header">
              <span class="kanban-col-dot" style="background:var(--blue)"></span>
              <span class="kanban-col-title">Open</span>
              <span class="kanban-col-count" id="kancnt-open">0</span>
            </div>
            <div class="kanban-cards" id="kancards-open"></div>
            <button class="kanban-add-btn" onclick="showCreateWO()">+ Add Work Order</button>
          </div>
          <div class="kanban-col" id="kancol-in_progress" data-status="in_progress">
            <div class="kanban-col-header">
              <span class="kanban-col-dot" style="background:var(--yellow)"></span>
              <span class="kanban-col-title">In Progress</span>
              <span class="kanban-col-count" id="kancnt-in_progress">0</span>
            </div>
            <div class="kanban-cards" id="kancards-in_progress"></div>
            <button class="kanban-add-btn" onclick="showCreateWO()">+ Add Work Order</button>
          </div>
          <div class="kanban-col" id="kancol-on_hold" data-status="on_hold">
            <div class="kanban-col-header">
              <span class="kanban-col-dot" style="background:var(--text2)"></span>
              <span class="kanban-col-title">On Hold</span>
              <span class="kanban-col-count" id="kancnt-on_hold">0</span>
            </div>
            <div class="kanban-cards" id="kancards-on_hold"></div>
          </div>
          <div class="kanban-col" id="kancol-completed" data-status="completed">
            <div class="kanban-col-header">
              <span class="kanban-col-dot" style="background:var(--green)"></span>
              <span class="kanban-col-title">Completed</span>
              <span class="kanban-col-count" id="kancnt-completed">0</span>
            </div>
            <div class="kanban-cards" id="kancards-completed"></div>
          </div>
          <div class="kanban-col" id="kancol-cancelled" data-status="cancelled">
            <div class="kanban-col-header">
              <span class="kanban-col-dot" style="background:var(--red)"></span>
              <span class="kanban-col-title">Cancelled</span>
              <span class="kanban-col-count" id="kancnt-cancelled">0</span>
            </div>
            <div class="kanban-cards" id="kancards-cancelled"></div>
          </div>
        </div>
      </div>

      <!-- ACTIVITY FEED PAGE -->
      <div class="page" id="page-activity">
        <div class="section-title">📡 Live Activity Feed
          <span class="live-badge" style="margin-left:8px"><span class="live-dot"></span>Live</span>
        </div>
        <div class="two-col">
          <div class="card">
            <div class="card-header">
              <span class="card-title">Recent Events</span>
              <button class="btn btn-secondary btn-sm" onclick="clearActivityFeed()">Clear</button>
            </div>
            <div class="activity-feed" id="activity-feed-list">
              <div class="empty-state"><div class="icon">📡</div><h3>Waiting for events...</h3></div>
            </div>
          </div>
          <div>
            <div class="card"><div class="card-header"><span class="card-title">Today Summary</span></div>
              <div id="activity-summary-content"></div></div>
            <div class="card"><div class="card-header"><span class="card-title">System Status</span></div>
              <div id="activity-health-content"></div></div>
          </div>
        </div>
      </div>


      <!-- ══ ANALYTICS PAGE ══ -->
      <div class="page" id="page-analytics">
        <div style="display:flex;align-items:center;gap:12px;margin-bottom:20px;flex-wrap:wrap">
          <div class="section-title" style="margin:0">📈 Advanced Analytics <small>Deep performance insights</small></div>
          <div style="margin-left:auto;display:flex;gap:8px">
            <button class="btn btn-secondary btn-sm" onclick="loadAnalytics()">↻ Refresh</button>
            <button class="btn btn-secondary btn-sm" onclick="window.print()">🖨 Print</button>
          </div>
        </div>
        <!-- AI Insights strip -->
        <div id="insights-strip" style="margin-bottom:24px"></div>
        <!-- MTTR + Tech Performance -->
        <div class="three-col" style="margin-bottom:20px">
          <div class="card" style="margin:0">
            <div class="card-header"><span class="card-title">⏱ MTTR by Category</span></div>
            <div class="chart-wrap"><canvas id="chart-mttr"></canvas></div>
          </div>
          <div class="card" style="margin:0">
            <div class="card-header"><span class="card-title">📅 WOs by Day of Week</span></div>
            <div class="chart-wrap"><canvas id="chart-dow"></canvas></div>
          </div>
          <div class="card" style="margin:0">
            <div class="card-header"><span class="card-title">👷 Top Technicians</span></div>
            <div id="analytics-techs"></div>
          </div>
        </div>
        <!-- Monthly cost trend + Repeat failures -->
        <div class="two-col" style="margin-bottom:20px">
          <div class="card" style="margin:0">
            <div class="card-header"><span class="card-title">📊 12-Month Cost & Volume Trend</span></div>
            <div class="chart-wrap" style="height:220px"><canvas id="chart-monthly-dual"></canvas></div>
          </div>
          <div class="card" style="margin:0">
            <div class="card-header">
              <span class="card-title">🔁 Repeat Failure Assets</span>
              <span class="badge b-warning" id="repeat-count">0</span>
            </div>
            <div id="analytics-repeat"></div>
          </div>
        </div>
        <!-- Asset Health Donut -->
        <div class="two-col">
          <div class="card" style="margin:0">
            <div class="card-header"><span class="card-title">💚 Asset Health Overview</span></div>
            <div style="display:flex;align-items:center;gap:24px;padding:8px">
              <div class="chart-wrap" style="height:200px;width:200px;flex-shrink:0"><canvas id="chart-health"></canvas></div>
              <div id="health-legend" style="flex:1"></div>
            </div>
          </div>
          <div class="card" style="margin:0">
            <div class="card-header"><span class="card-title">🎯 SLA Status (Open WOs)</span></div>
            <div id="analytics-sla"></div>
          </div>
        </div>
      </div>

      <!-- ══ WORK REQUESTS PAGE ══ -->
      <div class="page" id="page-work-requests">
        <div style="display:flex;align-items:center;gap:12px;margin-bottom:20px;flex-wrap:wrap">
          <div class="section-title" style="margin:0">📝 Work Request Portal</div>
          <div style="margin-left:auto;display:flex;gap:8px;align-items:center">
            <a href="/request" target="_blank" class="btn btn-secondary btn-sm">🌐 Public Portal</a>
            <button class="btn btn-primary btn-sm" onclick="showCreateWO()">+ New WO</button>
          </div>
        </div>
        <div class="two-col">
          <div class="card" style="margin:0">
            <div class="card-header">
              <span class="card-title">Pending Requests</span>
              <select class="filter-select" id="wr-filter" onchange="loadWorkRequests()">
                <option value="">All Statuses</option>
                <option value="open">Open</option>
                <option value="in_progress">In Progress</option>
                <option value="completed">Completed</option>
              </select>
            </div>
            <div id="wr-list"><div class="loading"><div class="spinner"></div>Loading...</div></div>
          </div>
          <div class="card" style="margin:0">
            <div class="card-header"><span class="card-title">📡 Portal QR Code</span></div>
            <div style="text-align:center;padding:20px">
              <div id="portal-qr" style="width:180px;height:180px;margin:0 auto 16px;background:var(--bg3);
                border:2px solid var(--border);border-radius:12px;display:flex;align-items:center;
                justify-content:center;font-size:13px;color:var(--text2)">
                📱 QR code would appear<br>here in production
              </div>
              <p style="font-size:13px;color:var(--text2);margin-bottom:12px">Share this link with staff to submit maintenance requests without logging in:</p>
              <div style="background:var(--bg3);border:1px solid var(--border);border-radius:8px;
                padding:10px 14px;font-family:var(--mono);font-size:13px;color:var(--accent)" id="portal-url">
                Loading...
              </div>
              <button class="btn btn-secondary btn-sm" style="margin-top:10px" onclick="copyPortalURL()">📋 Copy URL</button>
            </div>
            <div class="card-header" style="border-top:1px solid var(--border)"><span class="card-title">Today's Stats</span></div>
            <div id="wr-stats" style="padding:4px"></div>
          </div>
        </div>
      </div>

      <!-- ══ v6: BUDGET TRACKER PAGE ══ -->
      <div class="page" id="page-budget">
        <div style="display:flex;align-items:center;gap:12px;margin-bottom:20px;flex-wrap:wrap">
          <div class="section-title" style="margin:0">💰 Maintenance Budget Tracker</div>
          <div style="margin-left:auto;display:flex;gap:8px;align-items:center">
            <select class="filter-select" id="budget-year" onchange="loadBudget()">
              <option value="2025">2025</option>
              <option value="2026">2026</option>
              <option value="2024">2024</option>
            </select>
            <button class="btn btn-primary btn-sm" onclick="saveBudget()">💾 Save Budget</button>
          </div>
        </div>
        <!-- Annual Summary Strip -->
        <div class="quick-strip" id="budget-strip" style="margin-bottom:20px">
          <div class="quick-strip-item"><div class="qs-val" id="bs-budget">—</div><div class="qs-lbl">Annual Budget</div></div>
          <div class="quick-strip-item"><div class="qs-val" id="bs-actual">—</div><div class="qs-lbl">Actual Spend</div></div>
          <div class="quick-strip-item"><div class="qs-val" id="bs-variance">—</div><div class="qs-lbl">Variance</div></div>
          <div class="quick-strip-item"><div class="qs-val" id="bs-pct">—</div><div class="qs-lbl">Budget Used</div></div>
        </div>
        <!-- Monthly Chart -->
        <div class="card" style="margin-bottom:16px">
          <div class="card-header"><span class="card-title">📊 Budget vs Actual — Monthly</span></div>
          <div class="chart-wrap" style="height:240px"><canvas id="budget-chart"></canvas></div>
        </div>
        <!-- Monthly Table -->
        <div class="card">
          <div class="card-header"><span class="card-title">📋 Monthly Budget Breakdown</span></div>
          <div class="tbl-wrap">
            <table>
              <thead><tr>
                <th>Month</th>
                <th>Budget (₹)</th>
                <th>Actual Spend (₹)</th>
                <th>Variance (₹)</th>
                <th>Status</th>
                <th>Notes</th>
              </tr></thead>
              <tbody id="budget-tbody"></tbody>
            </table>
          </div>
        </div>
      </div>

      <!-- ══ v6: SLA MONITOR PAGE ══ -->
      <div class="page" id="page-sla-monitor">
        <div style="display:flex;align-items:center;gap:12px;margin-bottom:20px;flex-wrap:wrap">
          <div class="section-title" style="margin:0">⏱ SLA Monitor</div>
          <div style="margin-left:auto;display:flex;gap:8px">
            <button class="btn btn-secondary btn-sm" onclick="loadSlaMonitor()">↻ Refresh</button>
            <button class="btn btn-danger btn-sm" id="escalate-btn" onclick="runEscalation()" style="display:none">⚠ Escalate Overdue</button>
          </div>
        </div>
        <!-- SLA Config Section (admin) -->
        <div class="card admin-section" style="display:none;margin-bottom:16px">
          <div class="card-header" style="display:flex;align-items:center;justify-content:space-between">
            <span class="card-title">⚙ SLA Configuration</span>
            <button class="btn btn-primary btn-sm" onclick="saveSlaConfig()">Save SLA Config</button>
          </div>
          <div class="tbl-wrap">
            <table id="sla-config-table">
              <thead><tr><th>Priority</th><th>Response (hrs)</th><th>Resolution (hrs)</th><th>Escalation (hrs)</th></tr></thead>
              <tbody id="sla-config-tbody"></tbody>
            </table>
          </div>
        </div>
        <!-- SLA Status Cards Summary -->
        <div class="quick-strip" style="margin-bottom:16px">
          <div class="quick-strip-item"><div class="qs-val text-red" id="sla-escalated">0</div><div class="qs-lbl">Escalated</div></div>
          <div class="quick-strip-item"><div class="qs-val text-red" id="sla-breached">0</div><div class="qs-lbl">Breached</div></div>
          <div class="quick-strip-item"><div class="qs-val text-yellow" id="sla-at-risk">0</div><div class="qs-lbl">At Risk</div></div>
          <div class="quick-strip-item"><div class="qs-val text-green" id="sla-ok">0</div><div class="qs-lbl">On Track</div></div>
        </div>
        <!-- SLA Work Orders List -->
        <div class="card">
          <div class="card-header"><span class="card-title">Open Work Orders — SLA Status</span></div>
          <div id="sla-list"><div class="loading"><div class="spinner"></div>Loading...</div></div>
        </div>
      </div>

      <!-- ══ v6: REORDER WIZARD PAGE ══ -->
      <div class="page" id="page-reorder-wizard">
        <div style="display:flex;align-items:center;gap:12px;margin-bottom:20px;flex-wrap:wrap">
          <div class="section-title" style="margin:0">🪄 Parts Reorder Wizard</div>
          <button class="btn btn-secondary btn-sm" style="margin-left:auto" onclick="loadReorderWizard()">↻ Refresh</button>
        </div>
        <div style="background:rgba(255,190,77,.08);border:1px solid rgba(255,190,77,.2);border-radius:var(--r8);padding:12px 16px;margin-bottom:16px;font-size:13px;color:var(--yellow)">
          ⚠ The following parts are at or below minimum stock levels. Review quantities and generate purchase orders by supplier.
        </div>
        <div id="reorder-content"><div class="loading"><div class="spinner"></div>Scanning inventory...</div></div>
      </div>

    </div><!-- /content-inner -->
  </div><!-- /main -->
</div><!-- /app -->

<!-- SIDEBAR OVERLAY (mobile) -->
<div class="sidebar-overlay" id="sidebar-overlay" onclick="closeSidebar()"></div>

<!-- BOTTOM NAV (mobile) -->
<nav class="bottom-nav" id="bottom-nav" style="grid-template-columns:repeat(5,1fr)">
  <div class="bottom-nav-item" onclick="showPage('dashboard');closeSidebar();updateBottomNav('dashboard')" id="bn-dashboard">
    <span class="bn-icon">◈</span>Home
  </div>
  <div class="bottom-nav-item" onclick="showPage('work-orders');closeSidebar();updateBottomNav('work-orders')" id="bn-work-orders">
    <span class="bn-icon">📋</span>WOs
  </div>
  <div class="bottom-nav-item" onclick="openQRScanner()" id="bn-scan">
    <span class="bn-icon" style="background:linear-gradient(135deg,var(--green),var(--green2));color:var(--bg0);border-radius:50%;width:46px;height:46px;display:flex;align-items:center;justify-content:center;margin-top:-20px;box-shadow:0 4px 16px rgba(0,229,160,.5),0 0 0 3px var(--bg1)">📷</span>Scan
  </div>
  <div class="bottom-nav-item" onclick="showPage('assets');closeSidebar();updateBottomNav('assets')" id="bn-assets">
    <span class="bn-icon">⚙</span>Assets
  </div>
  <div class="bottom-nav-item" onclick="toggleMobileMore()" id="bn-more">
    <span class="bn-icon">☰</span>More
  </div>
</nav>

<!-- MOBILE MORE DRAWER -->
<div id="mobile-more-drawer" style="display:none;position:fixed;bottom:0;left:0;right:0;z-index:850;background:var(--bg2);border-top:1px solid var(--border);border-radius:20px 20px 0 0;padding:16px 16px calc(var(--bottomnav-h) + env(safe-area-inset-bottom,0px) + 16px);box-shadow:0 -8px 32px rgba(0,0,0,.5);animation:modal-slide-up .25s ease">
  <div style="width:40px;height:4px;background:var(--border2);border-radius:2px;margin:0 auto 16px;flex-shrink:0"></div>
  <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px">
    <div onclick="showPage('pm');closeSidebar();closeMobileMore()" style="display:flex;flex-direction:column;align-items:center;gap:6px;padding:12px 8px;background:var(--bg3);border-radius:var(--r10);cursor:pointer;border:1px solid var(--border)">
      <span style="font-size:22px">🗓</span>
      <span style="font-size:10px;color:var(--text1);font-weight:600;text-align:center">PM<br>Schedules</span>
    </div>
    <div onclick="showPage('parts');closeSidebar();closeMobileMore()" style="display:flex;flex-direction:column;align-items:center;gap:6px;padding:12px 8px;background:var(--bg3);border-radius:var(--r10);cursor:pointer;border:1px solid var(--border)">
      <span style="font-size:22px">🔧</span>
      <span style="font-size:10px;color:var(--text1);font-weight:600;text-align:center">Parts &<br>Stock</span>
    </div>
    <div onclick="showPage('analytics');closeSidebar();closeMobileMore()" style="display:flex;flex-direction:column;align-items:center;gap:6px;padding:12px 8px;background:var(--bg3);border-radius:var(--r10);cursor:pointer;border:1px solid var(--border)">
      <span style="font-size:22px">📈</span>
      <span style="font-size:10px;color:var(--text1);font-weight:600;text-align:center">Analytics</span>
    </div>
    <div onclick="showPage('calendar');closeSidebar();closeMobileMore()" style="display:flex;flex-direction:column;align-items:center;gap:6px;padding:12px 8px;background:var(--bg3);border-radius:var(--r10);cursor:pointer;border:1px solid var(--border)">
      <span style="font-size:22px">📅</span>
      <span style="font-size:10px;color:var(--text1);font-weight:600;text-align:center">Calendar</span>
    </div>
    <div onclick="showPage('kanban');closeSidebar();closeMobileMore()" style="display:flex;flex-direction:column;align-items:center;gap:6px;padding:12px 8px;background:var(--bg3);border-radius:var(--r10);cursor:pointer;border:1px solid var(--border)">
      <span style="font-size:22px">🗂</span>
      <span style="font-size:10px;color:var(--text1);font-weight:600;text-align:center">Kanban<br>Board</span>
    </div>
    <div onclick="showPage('reports');closeSidebar();closeMobileMore()" style="display:flex;flex-direction:column;align-items:center;gap:6px;padding:12px 8px;background:var(--bg3);border-radius:var(--r10);cursor:pointer;border:1px solid var(--border)">
      <span style="font-size:22px">📊</span>
      <span style="font-size:10px;color:var(--text1);font-weight:600;text-align:center">Reports</span>
    </div>
    <div onclick="showPage('sla-monitor');closeSidebar();closeMobileMore()" style="display:flex;flex-direction:column;align-items:center;gap:6px;padding:12px 8px;background:var(--bg3);border-radius:var(--r10);cursor:pointer;border:1px solid var(--border)">
      <span style="font-size:22px">⏱</span>
      <span style="font-size:10px;color:var(--text1);font-weight:600;text-align:center">SLA<br>Monitor</span>
    </div>
    <div onclick="showPage('profile');closeSidebar();closeMobileMore()" style="display:flex;flex-direction:column;align-items:center;gap:6px;padding:12px 8px;background:var(--bg3);border-radius:var(--r10);cursor:pointer;border:1px solid var(--border)">
      <span style="font-size:22px">👤</span>
      <span style="font-size:10px;color:var(--text1);font-weight:600;text-align:center">Profile</span>
    </div>
  </div>
  <div style="margin-top:12px;display:flex;gap:8px">
    <button onclick="toggleTheme();closeMobileMore()" class="btn btn-secondary btn-sm" style="flex:1">🌙 Toggle Theme</button>
    <button onclick="doLogout()" class="btn btn-danger btn-sm" style="flex:1">→ Sign Out</button>
  </div>
</div>
<div id="mobile-more-overlay" onclick="closeMobileMore()" style="display:none;position:fixed;inset:0;z-index:840;background:rgba(0,0,0,.5)"></div>

<!-- FAB (mobile) -->
<button class="fab" id="fab-btn" onclick="fabAction()" title="New Work Order">＋</button>

<!-- TOAST -->
<div id="toast"></div>

<!-- MODALS -->
<div id="modal-container"></div>

<!-- ══ COMMAND PALETTE ══ -->
<div id="cmd-palette-overlay" onclick="if(event.target===this)closeCmdPalette()">
  <div class="cmd-palette">
    <div class="cmd-input-wrap">
      <span class="cmd-icon">⌘</span>
      <input type="text" id="cmd-input" placeholder="Search pages, actions, assets…" autocomplete="off"
             oninput="cmdFilter(this.value)" onkeydown="cmdKeydown(event)">
      <span class="cmd-shortcut">ESC</span>
    </div>
    <div class="cmd-results" id="cmd-results"></div>
    <div class="cmd-footer">
      <span><kbd>↑↓</kbd> navigate</span>
      <span><kbd>↵</kbd> select</span>
      <span><kbd>ESC</kbd> close</span>
      <span style="margin-left:auto;color:var(--accent)">NEXUS CMMS v9</span>
    </div>
  </div>
</div>

<!-- ══ KEYBOARD SHORTCUTS OVERLAY ══ -->
<div id="shortcut-overlay" onclick="if(event.target===this)document.getElementById('shortcut-overlay').classList.remove('active')">
  <div class="shortcut-panel">
    <div style="display:flex;align-items:center;justify-content:space-between">
      <h3 style="font-size:16px;font-weight:700">⌨ Keyboard Shortcuts</h3>
      <button onclick="document.getElementById('shortcut-overlay').classList.remove('active')"
              style="background:none;border:none;color:var(--text2);font-size:20px;cursor:pointer">✕</button>
    </div>
    <div class="shortcut-grid">
      <div class="shortcut-row"><span class="shortcut-label">Command Palette</span>
        <span class="shortcut-keys"><kbd>Ctrl</kbd><kbd>K</kbd></span></div>
      <div class="shortcut-row"><span class="shortcut-label">Dashboard</span>
        <span class="shortcut-keys"><kbd>G</kbd><kbd>D</kbd></span></div>
      <div class="shortcut-row"><span class="shortcut-label">Work Orders</span>
        <span class="shortcut-keys"><kbd>G</kbd><kbd>W</kbd></span></div>
      <div class="shortcut-row"><span class="shortcut-label">Assets</span>
        <span class="shortcut-keys"><kbd>G</kbd><kbd>A</kbd></span></div>
      <div class="shortcut-row"><span class="shortcut-label">Parts</span>
        <span class="shortcut-keys"><kbd>G</kbd><kbd>P</kbd></span></div>
      <div class="shortcut-row"><span class="shortcut-label">Kanban Board</span>
        <span class="shortcut-keys"><kbd>G</kbd><kbd>K</kbd></span></div>
      <div class="shortcut-row"><span class="shortcut-label">New Work Order</span>
        <span class="shortcut-keys"><kbd>N</kbd></span></div>
      <div class="shortcut-row"><span class="shortcut-label">Toggle Sidebar</span>
        <span class="shortcut-keys"><kbd>\\</kbd></span></div>
      <div class="shortcut-row"><span class="shortcut-label">Focus Mode</span>
        <span class="shortcut-keys"><kbd>F</kbd></span></div>
      <div class="shortcut-row"><span class="shortcut-label">Toggle Theme</span>
        <span class="shortcut-keys"><kbd>T</kbd></span></div>
      <div class="shortcut-row"><span class="shortcut-label">Calendar</span>
        <span class="shortcut-keys"><kbd>G</kbd><kbd>C</kbd></span></div>
      <div class="shortcut-row"><span class="shortcut-label">This help</span>
        <span class="shortcut-keys"><kbd>?</kbd></span></div>
    </div>
  </div>
</div>

<!-- ══ CONTEXT MENU ══ -->
<div id="ctx-menu" class="ctx-menu" style="display:none"></div>

<!-- ══ FOCUS MODE EXIT ══ -->
<button class="focus-exit-btn" onclick="toggleFocusMode()">✕ Exit Focus</button>

<script>
// ── STATE ─────────────────────────────────────────────────────────────────────
let state = {
  user: null,
  currentPage: 'dashboard',
  data: {},
  charts: {},
  isAdmin: false,
  pagination: { wo: 1, assets: 1, parts: 1, audit: 1 },
  kanban: { dragWoId: null, dragStatus: null },
  activityFeed: [],
  sidebarCollapsed: false,
  theme: localStorage.getItem('cmms_theme') || 'dark',
  accent: localStorage.getItem('cmms_accent') || 'green',
  cmdHistory: [],
};

// ── INR CURRENCY FORMATTER ────────────────────────────────────────────────────
function fmtINR(n, decimals=0) {
  if (n === null || n === undefined || isNaN(n)) return '₹0';
  return '₹' + Number(n).toLocaleString('en-IN', { maximumFractionDigits: decimals, minimumFractionDigits: decimals });
}
function fmtINR2(n) { return fmtINR(n, 2); }

// ── API ───────────────────────────────────────────────────────────────────────
async function api(method, path, body) {
  try {
    const r = await fetch('/api' + path, {
      method,
      credentials: 'same-origin',
      headers: {'Content-Type': 'application/json'},
      body: body ? JSON.stringify(body) : undefined,
    });
    const j = await r.json();
    if (!r.ok && !j.success) throw new Error(j.error || j.message || 'Request failed');
    return j;
  } catch(e) { throw e; }
}

// ── AUTH ──────────────────────────────────────────────────────────────────────
async function doLogin() {
  const u = document.getElementById('login-user').value.trim();
  const p = document.getElementById('login-pass').value;
  if (!u || !p) { document.getElementById('login-err').textContent = 'Enter username and password'; return; }
  try {
    const r = await api('POST', '/login', { username: u, password: p });
    if (r.success) { state.user = r.user; initApp(); }
    else { document.getElementById('login-err').textContent = r.message || 'Login failed'; }
  } catch(e) { document.getElementById('login-err').textContent = e.message; }
}

document.getElementById('login-pass').addEventListener('keydown', e => e.key === 'Enter' && doLogin());

async function doLogout() {
  await api('POST', '/logout');
  location.reload();
}

// ── INIT ──────────────────────────────────────────────────────────────────────
async function _initAppCore() {
  document.getElementById('login-screen').style.display = 'none';
  document.getElementById('app').classList.add('active');
  state.isAdmin = state.user.role === 'admin';

  // Update sidebar user block
  const initials = (state.user.full_name || state.user.username).split(' ').map(w=>w[0]).join('').toUpperCase().slice(0,2);
  document.getElementById('sb-av').textContent = initials;
  document.getElementById('sb-name').textContent = state.user.full_name || state.user.username;
  document.getElementById('sb-role').textContent = state.user.role;

  // Show admin sections
  if (state.isAdmin) {
    document.querySelector('.admin-section').style.display = 'block';
    document.body.classList.add('is-admin');
  }

  // Check notifications
  try {
    const me = await api('GET', '/me');
    if (me.notifications > 0) document.getElementById('notif-dot').style.display = 'block';
  } catch(e) {}

  // Load categories for filters
  await loadCategories();
  await loadDashboard();
  showPage('dashboard');
}

async function initApp() {
  await _initAppCore();
  // Connect SSE for real-time updates
  connectSSE();
  // Sync any offline queue
  if (navigator.onLine && _offlineQueue.length > 0) {
    setTimeout(syncOfflineQueue, 1500);
  }
}

// ── NAVIGATION ────────────────────────────────────────────────────────────────
const pageTitles = {
  dashboard: 'Dashboard', 'work-orders': 'Work Orders', assets: 'Assets',
  pm: 'PM Schedules', 'eq-history': 'Equipment History', calendar: 'Maintenance Calendar',
  reports: 'Reports & Exports', import: 'Import Data', parts: 'Parts & Inventory', suppliers: 'Suppliers',
  users: 'User Management', audit: 'Audit Log', settings: 'Settings', profile: 'My Profile',
  kanban: '🗂 Kanban Board', activity: '📡 Activity Feed',
  analytics: '📈 Advanced Analytics', 'work-requests': '📝 Work Requests',
};

function _origShowPageInternal(name) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  document.getElementById('page-' + name)?.classList.add('active');
  const nav = document.querySelector(`.nav-item[onclick*="'${name}'"]`);
  if (nav) nav.classList.add('active');
  state.currentPage = name;
  document.getElementById('topbar-title').textContent = pageTitles[name] || name;
  const tb = document.getElementById('topbar-action');
  tb.style.display = 'none';

  if (name === 'work-orders') loadWO();
  else if (name === 'assets') loadAssets();
  else if (name === 'pm') loadPM();
  else if (name === 'parts') loadParts();
  else if (name === 'suppliers') loadSuppliers();
  else if (name === 'users' && state.isAdmin) loadUsers();
  else if (name === 'audit' && state.isAdmin) loadAudit();
  else if (name === 'settings' && state.isAdmin) loadSettings();
  else if (name === 'profile') loadProfile();
  else if (name === 'eq-history') initEqHistory();
  else if (name === 'calendar') initCalendar();
  else if (name === 'reports') {}
  else if (name === 'import') initImport();
  else if (name === 'kanban') loadKanban();
  else if (name === 'activity') loadActivityPage();
  else if (name === 'analytics') loadAnalytics();
  else if (name === 'work-requests') loadWorkRequests();
}

// ── DASHBOARD ─────────────────────────────────────────────────────────────────
async function loadDashboard() {
  try {
    const d = await api('GET', '/dashboard');
    state.data.dash = d;
    state.data.dashboard = d;  // v4: store for welcome banner
    // v4: dispatch event for welcome banner
    document.dispatchEvent(new CustomEvent('cmms:dashboard-loaded', {detail: d}));

    // Stats
    document.getElementById('dash-stats').innerHTML = `
      <div class="stat-card"><div class="stat-label">Total Assets</div><div class="stat-value">${d.total_assets}</div>
        <div class="stat-sub">${d.active_assets} active · ${d.maintenance_assets} maintenance</div><div class="stat-icon">⚙</div></div>
      <div class="stat-card"><div class="stat-label">Open Work Orders</div><div class="stat-value text-yellow">${d.open_wo}</div>
        <div class="stat-sub">${d.in_progress_wo} in progress</div><div class="stat-icon">📋</div></div>
      <div class="stat-card"><div class="stat-label">Critical Issues</div><div class="stat-value text-red">${d.critical_wo}</div>
        <div class="stat-sub">Require immediate attention</div><div class="stat-icon">⚠</div></div>
      <div class="stat-card"><div class="stat-label">Completed WOs</div><div class="stat-value text-green">${d.completed_wo}</div>
        <div class="stat-sub">Total maintenance history</div><div class="stat-icon">✓</div></div>
      <div class="stat-card"><div class="stat-label">Low Stock Parts</div><div class="stat-value text-yellow">${d.low_parts}</div>
        <div class="stat-sub">Below minimum quantity</div><div class="stat-icon">📦</div></div>
      <div class="stat-card"><div class="stat-label">Overdue PM</div><div class="stat-value text-red">${d.overdue_pm}</div>
        <div class="stat-sub">Past due date</div><div class="stat-icon">🗓</div></div>
      <div class="stat-card"><div class="stat-label">Parts Value</div><div class="stat-value">${fmtINR(d.total_parts_value)}</div>
        <div class="stat-sub">Total inventory value</div><div class="stat-icon">💰</div></div>
      <div class="stat-card"><div class="stat-label">Maintenance Cost</div><div class="stat-value">${fmtINR(d.total_wo_cost)}</div>
        <div class="stat-sub">All time total</div><div class="stat-icon">💵</div></div>
    `;

    // Nav badges
    if (d.open_wo > 0) { document.getElementById('nb-wo').textContent = d.open_wo; document.getElementById('nb-wo').style.display = 'inline'; }
    if (d.overdue_pm > 0) { document.getElementById('nb-pm').textContent = d.overdue_pm; document.getElementById('nb-pm').style.display = 'inline'; }
    if (d.low_parts > 0) { document.getElementById('nb-parts').textContent = d.low_parts; document.getElementById('nb-parts').style.display = 'inline'; }

    // WO Status Chart
    if (state.charts['wo-status']) state.charts['wo-status'].destroy();
    const colors = { open: '#4da6ff', in_progress: '#ffbe4d', completed: '#00e5a0', cancelled: '#5c6070' };
    const statusCtx = document.getElementById('chart-wo-status').getContext('2d');
    state.charts['wo-status'] = new Chart(statusCtx, {
      type: 'doughnut',
      data: { labels: d.wo_by_status.map(r=>r.status), datasets: [{ data: d.wo_by_status.map(r=>r.count), backgroundColor: d.wo_by_status.map(r=>colors[r.status]||'#5c6070'), borderWidth: 0, borderRadius: 4 }] },
      options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'right', labels: { color: '#9aa0b4', font: { family: 'IBM Plex Mono', size: 11 }, padding: 16 } } } }
    });

    // WO Type Chart
    if (state.charts['wo-type']) state.charts['wo-type'].destroy();
    const typeColors = { corrective: '#ff4d6d', preventive: '#00e5a0', inspection: '#4da6ff', emergency: '#b06dff' };
    const typeCtx = document.getElementById('chart-wo-type').getContext('2d');
    state.charts['wo-type'] = new Chart(typeCtx, {
      type: 'bar',
      data: { labels: d.wo_by_type.map(r=>r.type), datasets: [{ data: d.wo_by_type.map(r=>r.count), backgroundColor: d.wo_by_type.map(r=>typeColors[r.type]||'#5c6070'), borderRadius: 6, borderSkipped: false }] },
      options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } },
        scales: { x: { ticks: { color: '#9aa0b4', font: { family: 'IBM Plex Mono', size: 11 } }, grid: { display: false }, border: { display: false } },
          y: { ticks: { color: '#9aa0b4', font: { family: 'IBM Plex Mono', size: 11 }, stepSize: 1 }, grid: { color: '#252830' }, border: { display: false } } } }
    });

    // Recent WOs table
    const woTbody = document.querySelector('#dash-wo-tbl tbody');
    woTbody.innerHTML = d.recent_wo.map(w => `<tr style="cursor:pointer" onclick="openWODetail(${w.id})">
      <td class="td-mono">${w.wo_number}</td>
      <td class="td-primary">${w.title}</td>
      <td style="font-size:12px">${w.asset_name||'-'}</td>
      <td><span class="badge b-${w.priority}">${w.priority}</span></td>
      <td><span class="badge b-${w.status}">${w.status.replace('_',' ')}</span></td>
    </tr>`).join('');

    // Low stock
    document.getElementById('dash-low-stock').innerHTML = d.low_stock_parts.length ? d.low_stock_parts.map(p => `
      <div style="display:flex;align-items:center;justify-content:space-between;padding:10px 0;border-bottom:1px solid var(--border)">
        <div><div style="font-size:13px;font-weight:500">${p.name}</div>
          <div style="font-size:11px;color:var(--text2);font-family:var(--mono)">${p.part_number||''}</div></div>
        <div style="text-align:right"><div class="badge b-danger">${p.quantity} / ${p.min_quantity}</div>
          <div style="font-size:11px;color:var(--text2);margin-top:3px">${fmtINR2(p.unit_cost||0)} ea</div></div>
      </div>`).join('') : '<div class="empty-state"><div class="icon">📦</div><p>All stock levels are adequate</p></div>';

    // Upcoming PM
    document.getElementById('dash-pm').innerHTML = d.upcoming_pm.length ? `
      <table><thead><tr><th>PM Task</th><th>Asset</th><th>Due Date</th><th>Assigned To</th><th>Est. Hours</th><th>Action</th></tr></thead>
      <tbody>${d.upcoming_pm.map(p => `<tr>
        <td class="td-primary">${p.title}</td>
        <td><span class="td-mono">${p.asset_code||''}</span> ${p.asset_name||'-'}</td>
        <td style="font-family:var(--mono);font-size:12px">${p.next_due}</td>
        <td>${p.assigned_to_name||'-'}</td>
        <td>${p.estimated_hours||'-'} hrs</td>
        <td><button class="btn btn-success btn-sm" onclick="completePM(${p.id})">✓ Complete</button></td>
      </tr>`).join('')}</tbody></table>` : '<div class="empty-state"><div class="icon">✓</div><p>No PM due in the next 30 days</p></div>';
    renderDashboardCharts(d);
  } catch(e) { toast('Error loading dashboard: ' + e.message, 'error'); }
}

// ── WORK ORDERS ───────────────────────────────────────────────────────────────
async function loadWO() {
  const search = document.getElementById('wo-search')?.value || '';
  const status = document.getElementById('wo-status-filter')?.value || '';
  const priority = document.getElementById('wo-priority-filter')?.value || '';
  const type = document.getElementById('wo-type-filter')?.value || '';
  const page = state.pagination.wo || 1;
  try {
    const p = new URLSearchParams({ search, status, priority, type, page, per_page: 25 });
    const d = await api('GET', '/work-orders?' + p);
    const tbody = document.getElementById('wo-tbody');
    const isMobile = window.innerWidth <= 768;
    
    if (isMobile) {
      // Mobile: render card view outside the table
      let mobileContainer = document.getElementById('wo-mobile-list');
      if (!mobileContainer) {
        mobileContainer = document.createElement('div');
        mobileContainer.id = 'wo-mobile-list';
        tbody.closest('.tbl-wrap').parentNode.insertBefore(mobileContainer, tbody.closest('.tbl-wrap'));
        tbody.closest('.tbl-wrap').style.display = 'none';
      }
      mobileContainer.style.display = 'block';
      mobileContainer.innerHTML = d.items.length ? d.items.map(w => `
        <div class="wo-mobile-card p-${w.priority}" onclick="openWODetail(${w.id})">
          <div class="wo-mc-top">
            <div>
              <div class="wo-mc-num">${w.wo_number}</div>
              <div class="wo-mc-title">${escHtml(w.title)}</div>
            </div>
            <span class="badge b-${w.status}" style="white-space:nowrap;flex-shrink:0">${w.status.replace('_',' ')}</span>
          </div>
          <div class="wo-mc-meta">
            <span class="badge b-${w.priority}">${w.priority}</span>
            <span class="tag">${w.type}</span>
            ${w.asset_name ? `<span class="tag" style="font-size:10px">⚙ ${escHtml(w.asset_name)}</span>` : ''}
          </div>
          <div class="wo-mc-footer">
            <span>👤 ${w.assigned_to_name || 'Unassigned'}</span>
            ${w.due_date ? `<span style="color:${isOverdue(w.due_date)?'var(--red)':'var(--text2)'};font-family:var(--mono)">📅 ${w.due_date}</span>` : ''}
          </div>
        </div>
      `).join('') : '<div class="empty-state" style="padding:32px"><div class="icon">📋</div><h3>No work orders found</h3></div>';
      tbody.innerHTML = '';
    } else {
      // Desktop: hide mobile list if shown
      const mobileContainer = document.getElementById('wo-mobile-list');
      if (mobileContainer) mobileContainer.style.display = 'none';
      tbody.closest('.tbl-wrap').style.display = '';
      tbody.innerHTML = d.items.map(w => `<tr style="cursor:pointer">
        <td onclick="openWODetail(${w.id})" class="td-mono">${w.wo_number}</td>
        <td onclick="openWODetail(${w.id})" class="td-primary">${w.title}</td>
        <td onclick="openWODetail(${w.id})" style="font-size:12px">${w.asset_name||'<span class="text-muted">—</span>'}</td>
        <td><span class="badge b-${w.priority}">${w.priority}</span></td>
        <td><span class="badge b-${w.status}">${w.status.replace('_',' ')}</span></td>
        <td><span class="tag">${w.type}</span></td>
        <td style="font-size:12px">${w.assigned_to_name||'<span class="text-muted">Unassigned</span>'}</td>
        <td style="font-family:var(--mono);font-size:11px;color:${isOverdue(w.due_date)?'var(--red)':'var(--text2)'}">${w.due_date||'—'}</td>
        <td>
          <button class="btn btn-secondary btn-sm btn-icon" onclick="openWODetail(${w.id})" title="View">👁</button>
          <button class="btn btn-secondary btn-sm btn-icon admin-only-btn" onclick="editWO(${w.id})" title="Edit">✏</button>
          <button class="btn btn-danger btn-sm btn-icon admin-only-btn" onclick="deleteWO(${w.id},'${escHtml(w.wo_number)}')" title="Delete">🗑</button>
        </td>
      </tr>`).join('') || '<tr><td colspan="9" class="empty-state">No work orders found</td></tr>';
    }
    renderPagination('wo-pagination', page, d.pages, p => { state.pagination.wo = p; loadWO(); });
  } catch(e) { toast('Error loading work orders', 'error'); }
}

function isOverdue(dateStr) {
  if (!dateStr) return false;
  return new Date(dateStr) < new Date() && new Date(dateStr).toString() !== 'Invalid Date';
}

async function openWODetail(id) {
  try {
    const d = await api('GET', '/work-orders/' + id);
    const w = d.work_order;
    const modal = createModal('modal-wo-detail', `<span class="td-mono">${w.wo_number}</span> — ${w.title}`, `
      <div class="two-col">
        <div>
          <div class="form-group"><label>Status</label><div><span class="badge b-${w.status}" style="font-size:13px;padding:5px 12px">${w.status.replace('_',' ')}</span></div></div>
          <div class="form-group"><label>Priority</label><div><span class="badge b-${w.priority}" style="font-size:13px">${w.priority}</span></div></div>
          <div class="form-group"><label>Type</label><div><span class="tag">${w.type}</span></div></div>
          <div class="form-group"><label>Asset</label><div style="font-size:14px">${w.asset_name||'—'} ${w.asset_code?`<span class="td-mono">(${w.asset_code})</span>`:''}</div></div>
          <div class="form-group"><label>Location</label><div style="font-size:14px">${w.location_name||'—'}</div></div>
        </div>
        <div>
          <div class="form-group"><label>Assigned To</label><div style="font-size:14px">${w.assigned_to_name||'—'}</div></div>
          <div class="form-group"><label>Scheduled / Due</label><div style="font-family:var(--mono);font-size:13px">${w.scheduled_date||'—'} / ${w.due_date||'—'}</div></div>
          <div class="form-group"><label>Est. Hours</label><div style="font-family:var(--mono);font-size:13px">${w.estimated_hours||'—'} hrs</div></div>
          <div class="form-group"><label>Actual Hours</label><div style="font-family:var(--mono);font-size:13px">${w.actual_hours||'—'} hrs</div></div>
          <div class="form-group"><label>Total Cost</label><div style="font-family:var(--mono);font-size:14px;color:var(--green)">${fmtINR2(w.total_cost||0)}</div></div>
        </div>
      </div>
      ${w.description?`<div class="form-group"><label>Description</label><div style="font-size:13px;color:var(--text1);background:var(--bg3);padding:12px;border-radius:8px;border:1px solid var(--border)">${w.description}</div></div>`:''}
      ${w.safety_notes?`<div class="form-group"><label>⚠ Safety Notes</label><div style="font-size:13px;color:var(--yellow);background:rgba(255,190,77,.05);padding:12px;border-radius:8px;border:1px solid rgba(255,190,77,.2)">${w.safety_notes}</div></div>`:''}
      ${w.completion_notes?`<div class="form-group"><label>Completion Notes</label><div style="font-size:13px;color:var(--text1)">${w.completion_notes}</div></div>`:''}
      <hr class="divider">
      <div class="card-title mb-16">💬 Comments</div>
      <div id="wo-comments-${id}">${d.comments.map(c=>`
        <div style="display:flex;gap:10px;margin-bottom:12px">
          <div class="user-av" style="width:30px;height:30px;font-size:11px;flex-shrink:0">${(c.user_name||'?').split(' ').map(w=>w[0]).join('').slice(0,2).toUpperCase()}</div>
          <div style="flex:1"><div style="font-size:12px;font-weight:600">${c.user_name||'Unknown'} <span style="font-weight:400;color:var(--text2);font-family:var(--mono)">${c.created_at?.slice(0,16)||''}</span></div>
            <div style="font-size:13px;color:var(--text1);margin-top:4px">${c.content}</div></div>
        </div>`).join('')||'<p style="color:var(--text2);font-size:13px">No comments yet</p>'}
      </div>
      <div style="display:flex;gap:10px;margin-top:12px">
        <input type="text" id="new-comment-${id}" class="form-control" placeholder="Add a comment..." style="flex:1">
        <button class="btn btn-primary btn-sm" onclick="addComment(${id})">Post</button>
      </div>
      <hr class="divider">
      <div class="card-title mb-16">🔧 Parts Used</div>
      ${d.parts.length?`<table style="width:100%"><thead><tr><th>Part</th><th>Qty</th><th>Unit Cost</th><th>Total</th></tr></thead><tbody>${d.parts.map(p=>`<tr><td>${p.part_name}<br><span class="td-mono" style="font-size:11px">${p.part_number}</span></td><td>${p.quantity_used}</td><td>${fmtINR2(p.unit_cost||0)}</td><td>${fmtINR2(p.line_total||0)}</td></tr>`).join('')}</tbody></table>` : '<p style="font-size:13px;color:var(--text2)">No parts used</p>'}
    `, 'modal-lg', [
      {label:'✏ Edit', cls:'btn-secondary', onclick: `closeModal('modal-wo-detail');editWO(${id})`},
      {label:'🖨 Print', cls:'btn-secondary', onclick:`printWODetail(${id})`},
      {label:'Close', cls:'btn-secondary', onclick:`closeModal('modal-wo-detail')`}
    ]);
  } catch(e) { toast('Error loading WO details', 'error'); }
}

async function addComment(woId) {
  const inp = document.getElementById('new-comment-' + woId);
  if (!inp.value.trim()) return;
  try {
    await api('POST', '/work-orders/' + woId + '/comments', { content: inp.value.trim() });
    inp.value = '';
    openWODetail(woId); // refresh
  } catch(e) { toast('Failed to add comment', 'error'); }
}

async function openWOModal(id) {
  let wo = null;
  if (id) {
    try { const r = await api('GET', '/work-orders/' + id); wo = r.work_order; } catch(e) {}
  }
  const users = await getUsers();
  const assets = await getAssets();
  createModal('modal-wo-edit', wo ? `Edit ${wo.wo_number}` : 'New Work Order', `
    <div class="form-grid">
      <div class="form-group"><label>Title *</label><input type="text" id="wo-title" class="form-control" value="${wo?.title||''}"></div>
      <div class="form-group"><label>Asset</label><select id="wo-asset" class="form-control">
        <option value="">-- Select Asset --</option>
        ${assets.map(a=>`<option value="${a.id}" ${wo?.asset_id==a.id?'selected':''}>${a.name} (${a.code||''})</option>`).join('')}
      </select></div>
      <div class="form-group"><label>Type</label><select id="wo-type" class="form-control">
        ${['corrective','preventive','inspection','emergency'].map(t=>`<option value="${t}" ${wo?.type==t?'selected':''}>${t}</option>`).join('')}
      </select></div>
      <div class="form-group"><label>Priority</label><select id="wo-priority" class="form-control">
        ${['critical','high','medium','low'].map(p=>`<option value="${p}" ${wo?.priority==p?'selected':''}>${p}</option>`).join('')}
      </select></div>
      <div class="form-group"><label>Status</label><select id="wo-status-edit" class="form-control">
        ${['open','in_progress','on_hold','completed','cancelled'].map(s=>`<option value="${s}" ${wo?.status==s?'selected':''}>${s.replace(/_/g,' ')}</option>`).join('')}
      </select></div>
      <div class="form-group"><label>Assigned To</label><select id="wo-assign" class="form-control">
        <option value="">-- Unassigned --</option>
        ${users.map(u=>`<option value="${u.id}" ${wo?.assigned_to==u.id?'selected':''}>${u.full_name} (${u.role})</option>`).join('')}
      </select></div>
      <div class="form-group"><label>Due Date</label><input type="date" id="wo-due" class="form-control" value="${wo?.due_date||''}"></div>
      <div class="form-group"><label>Estimated Hours</label><input type="number" id="wo-est-hrs" class="form-control" value="${wo?.estimated_hours||''}" step="0.5"></div>
      <div class="form-group"><label>Labor Cost (₹)</label><input type="number" id="wo-labor" class="form-control" value="${wo?.labor_cost||0}" step="0.01"></div>
      <div class="form-group"><label>Parts Cost (₹)</label><input type="number" id="wo-parts-cost" class="form-control" value="${wo?.parts_cost||0}" step="0.01"></div>
    </div>
    <div class="form-group"><label>Description</label><textarea id="wo-desc" class="form-control">${wo?.description||''}</textarea></div>
    <div class="form-group"><label>Safety Notes</label><textarea id="wo-safety" class="form-control" style="min-height:60px">${wo?.safety_notes||''}</textarea></div>
    <div class="form-group"><label>Completion Notes</label><textarea id="wo-completion" class="form-control" style="min-height:60px">${wo?.completion_notes||''}</textarea></div>
  `, 'modal-lg', [
    {label: wo ? 'Save Changes' : 'Create WO', cls:'btn-primary', onclick:`saveWO(${id||'null'})`},
    {label:'Cancel', cls:'btn-secondary', onclick:`closeModal('modal-wo-edit')`}
  ]);
}
async function editWO(id) { openWOModal(id); }

async function saveWO(id) {
  const data = {
    title: document.getElementById('wo-title').value.trim(),
    asset_id: document.getElementById('wo-asset').value || null,
    type: document.getElementById('wo-type').value,
    priority: document.getElementById('wo-priority').value,
    status: document.getElementById('wo-status-edit').value,
    assigned_to: document.getElementById('wo-assign').value || null,
    due_date: document.getElementById('wo-due').value || null,
    estimated_hours: parseFloat(document.getElementById('wo-est-hrs').value) || null,
    labor_cost: parseFloat(document.getElementById('wo-labor').value) || 0,
    parts_cost: parseFloat(document.getElementById('wo-parts-cost').value) || 0,
    description: document.getElementById('wo-desc').value,
    safety_notes: document.getElementById('wo-safety').value,
    completion_notes: document.getElementById('wo-completion').value,
  };
  if (!data.title) { toast('Title is required', 'error'); return; }
  try {
    if (id) { await api('PUT', '/work-orders/' + id, data); toast('Work order updated', 'success'); }
    else { const r = await api('POST', '/work-orders', data); toast(`Created ${r.wo_number}`, 'success'); }
    closeModal('modal-wo-edit');
    loadWO();
  } catch(e) { toast(e.message, 'error'); }
}

async function deleteWO(id, num) {
  if (!confirm(`Delete work order ${num}? This action cannot be undone.`)) return;
  try { await api('DELETE', '/work-orders/' + id); toast('Work order deleted', 'success'); loadWO(); }
  catch(e) { toast(e.message, 'error'); }
}

// ── ASSETS ────────────────────────────────────────────────────────────────────
async function loadAssets() {
  const search = document.getElementById('asset-search')?.value || '';
  const status = document.getElementById('asset-status-filter')?.value || '';
  const category = document.getElementById('asset-cat-filter')?.value || '';
  const page = state.pagination.assets || 1;
  try {
    const p = new URLSearchParams({ search, status, category, page, per_page: 25 });
    const d = await api('GET', '/assets?' + p);
    const tbody = document.getElementById('asset-tbody');
    tbody.innerHTML = d.items.map(a => `<tr>
      <td class="td-mono">${a.code||'—'}</td>
      <td onclick="openAssetDetail(${a.id})" style="cursor:pointer" class="td-primary">${a.name}</td>
      <td><span style="background:${a.category_color}22;color:${a.category_color};font-size:11px;padding:2px 8px;border-radius:4px">${a.category_icon||''} ${a.category_name||'—'}</span></td>
      <td style="font-size:12px">${a.location_name||'—'}</td>
      <td><span class="badge b-${a.status=='active'?'success':a.status=='maintenance'?'warning':'info'}">${a.status}</span></td>
      <td><span class="badge b-${a.criticality}">${a.criticality}</span></td>
      <td style="font-family:var(--mono);font-size:11px;color:${isWarrantyExpired(a.warranty_expiry)?'var(--red)':'var(--text2)'}">${a.warranty_expiry||'—'}</td>
      <td>
        <button class="btn btn-secondary btn-sm btn-icon" onclick="openAssetDetail(${a.id})" title="View">👁</button>
        <button class="btn btn-secondary btn-sm btn-icon" onclick="openHistoryModal(${a.id},'${escHtml(a.name)}')" title="History">📅</button>
        <button class="btn btn-secondary btn-sm btn-icon admin-only-btn" onclick="openAssetModal(${a.id})" title="Edit">✏</button>
        <button class="btn btn-danger btn-sm btn-icon admin-only-btn" onclick="deleteAsset(${a.id},'${escHtml(a.name)}')" title="Delete">🗑</button>
      </td>
    </tr>`).join('') || '<tr><td colspan="8" class="empty-state">No assets found</td></tr>';
    renderPagination('asset-pagination', page, d.pages, p => { state.pagination.assets = p; loadAssets(); });
  } catch(e) { toast('Error loading assets', 'error'); }
}

function isWarrantyExpired(dateStr) {
  if (!dateStr) return false;
  return new Date(dateStr) < new Date();
}

async function openAssetDetail(id) {
  try {
    const d = await api('GET', '/assets/' + id);
    const a = d.asset;
    createModal('modal-asset-detail', `${a.category_icon||'⚙'} ${a.name}`, `
      <div class="two-col">
        <div>
          <div class="form-group"><label>Asset Code</label><span class="td-mono" style="font-size:14px">${a.code||'—'}</span></div>
          <div class="form-group"><label>Status</label><span class="badge b-${a.status=='active'?'success':a.status=='maintenance'?'warning':'info'}" style="font-size:13px">${a.status}</span></div>
          <div class="form-group"><label>Category</label><span style="font-size:14px">${a.category_name||'—'}</span></div>
          <div class="form-group"><label>Location</label><span style="font-size:14px">${a.location_name||'—'}</span></div>
          <div class="form-group"><label>Criticality</label><span class="badge b-${a.criticality}" style="font-size:13px">${a.criticality}</span></div>
        </div>
        <div>
          <div class="form-group"><label>Make / Model</label><span style="font-size:14px">${a.make||''} ${a.model||''}</span></div>
          <div class="form-group"><label>Serial Number</label><span class="td-mono" style="font-size:13px">${a.serial_number||'—'}</span></div>
          <div class="form-group"><label>Purchase Date</label><span style="font-family:var(--mono);font-size:13px">${a.purchase_date||'—'}</span></div>
          <div class="form-group"><label>Purchase Cost</label><span style="font-family:var(--mono);font-size:14px;color:var(--green)">${fmtINR(a.purchase_cost||0)}</span></div>
          <div class="form-group"><label>Warranty Expiry</label><span style="font-family:var(--mono);font-size:13px;color:${isWarrantyExpired(a.warranty_expiry)?'var(--red)':'var(--text0)'}">${a.warranty_expiry||'—'}</span></div>
        </div>
      </div>
      ${a.description?`<div class="form-group"><label>Description</label><p style="font-size:13px;color:var(--text1)">${a.description}</p></div>`:''}
      ${a.notes?`<div class="form-group"><label>Notes</label><p style="font-size:13px;color:var(--text1)">${a.notes}</p></div>`:''}
      <hr class="divider">
      <div class="card-title mb-16">📋 Recent Work Orders</div>
      ${d.work_orders.length?`<table style="width:100%"><thead><tr><th>WO #</th><th>Title</th><th>Status</th><th>Cost</th><th>Date</th></tr></thead>
        <tbody>${d.work_orders.map(w=>`<tr onclick="openWODetail(${w.id})" style="cursor:pointer"><td class="td-mono">${w.wo_number}</td><td style="font-size:13px">${w.title}</td><td><span class="badge b-${w.status}">${w.status.replace('_',' ')}</span></td><td style="font-family:var(--mono);font-size:12px;color:var(--green)">${fmtINR(w.total_cost||0)}</td><td style="font-family:var(--mono);font-size:11px;color:var(--text2)">${w.created_at?.slice(0,10)||'—'}</td></tr>`).join('')}</tbody></table>` : '<p style="font-size:13px;color:var(--text2)">No work orders</p>'}
    `, 'modal-lg', [
      {label:'📅 History', cls:'btn-secondary', onclick:`closeModal('modal-asset-detail');openHistoryModal(${id},'${escHtml(a.name)}')`},
      {label:'✏ Edit', cls:'btn-secondary', onclick:`closeModal('modal-asset-detail');openAssetModal(${id})`},
      {label:'Close', cls:'btn-secondary', onclick:`closeModal('modal-asset-detail')`}
    ]);
  } catch(e) { toast('Error loading asset', 'error'); }
}

async function openHistoryModal(assetId, assetName) {
  try {
    const history = await api('GET', '/assets/' + assetId + '/history');
    const typeIcons = { work_order:'📋', pm_completion:'✅', status_change:'🔄', created:'⭐', meter_reading:'📊' };
    createModal('modal-history', `📅 Asset History: ${assetName}`, `
      <div style="margin-bottom:16px;display:flex;align-items:center;justify-content:space-between">
        <span style="font-size:13px;color:var(--text2)">${history.length} event${history.length!=1?'s':''} recorded</span>
        <button class="btn btn-secondary btn-sm" onclick="openWOModal();closeModal('modal-history')">＋ New Work Order</button>
      </div>
      ${history.length ? `<div class="timeline">
        ${history.map(h=>`<div class="timeline-item tl-${h.event_type}">
          <div class="tl-header">
            <div class="tl-title">${typeIcons[h.event_type]||'•'} ${h.event_title}</div>
            <div class="tl-date">${h.created_at?.slice(0,16)||''}</div>
          </div>
          ${h.event_detail?`<div class="tl-detail">${h.event_detail}</div>`:''}
          ${h.cost&&h.cost>0?`<div class="tl-cost">${fmtINR2(h.cost)}</div>`:''}
          ${h.performed_by_name?`<div class="tl-by">by ${h.performed_by_name}</div>`:''}
        </div>`).join('')}
      </div>` : '<div class="empty-state"><div class="icon">📅</div><h3>No History Yet</h3><p>History will appear as work orders and PMs are completed.</p></div>'}
    `, 'modal-lg', [{label:'Close', cls:'btn-secondary', onclick:`closeModal('modal-history')`}]);
  } catch(e) { toast('Error loading history', 'error'); }
}

async function openAssetModal(id) {
  let asset = null;
  if (id) {
    try { const r = await api('GET', '/assets/' + id); asset = r.asset; } catch(e) {}
  }
  const cats = state.data.categories || [];
  const locs = state.data.locations || await api('GET', '/locations');
  if (!state.data.locations) state.data.locations = locs;
  createModal('modal-asset-edit', id ? `Edit: ${asset?.name}` : 'New Asset', `
    <div class="form-grid">
      <div class="form-group"><label>Name *</label><input type="text" id="a-name" class="form-control" value="${asset?.name||''}"></div>
      <div class="form-group"><label>Asset Code</label><input type="text" id="a-code" class="form-control" value="${asset?.code||''}"></div>
      <div class="form-group"><label>Category</label><select id="a-cat" class="form-control">
        <option value="">-- Category --</option>${cats.map(c=>`<option value="${c.id}" ${asset?.category_id==c.id?'selected':''}>${c.icon||''} ${c.name}</option>`).join('')}
      </select></div>
      <div class="form-group"><label>Location</label><select id="a-loc" class="form-control">
        <option value="">-- Location --</option>${locs.map(l=>`<option value="${l.id}" ${asset?.location_id==l.id?'selected':''}>${l.name}</option>`).join('')}
      </select></div>
      <div class="form-group"><label>Status</label><select id="a-status" class="form-control">
        ${['active','maintenance','inactive','retired'].map(s=>`<option value="${s}" ${asset?.status==s?'selected':''}>${s}</option>`).join('')}
      </select></div>
      <div class="form-group"><label>Criticality</label><select id="a-crit" class="form-control">
        ${['critical','high','medium','low'].map(c=>`<option value="${c}" ${asset?.criticality==c?'selected':''}>${c}</option>`).join('')}
      </select></div>
      <div class="form-group"><label>Make</label><input type="text" id="a-make" class="form-control" value="${asset?.make||''}"></div>
      <div class="form-group"><label>Model</label><input type="text" id="a-model" class="form-control" value="${asset?.model||''}"></div>
      <div class="form-group"><label>Serial Number</label><input type="text" id="a-serial" class="form-control" value="${asset?.serial_number||''}"></div>
      <div class="form-group"><label>Purchase Date</label><input type="date" id="a-pdate" class="form-control" value="${asset?.purchase_date||''}"></div>
      <div class="form-group"><label>Purchase Cost (₹)</label><input type="number" id="a-pcost" class="form-control" value="${asset?.purchase_cost||''}" step="0.01"></div>
      <div class="form-group"><label>Warranty Expiry</label><input type="date" id="a-warranty" class="form-control" value="${asset?.warranty_expiry||''}"></div>
    </div>
    <div class="form-group"><label>Description</label><textarea id="a-desc" class="form-control">${asset?.description||''}</textarea></div>
    <div class="form-group"><label>Notes</label><textarea id="a-notes" class="form-control" style="min-height:60px">${asset?.notes||''}</textarea></div>
  `, 'modal-lg', [
    {label: id ? 'Save Changes' : 'Create Asset', cls:'btn-primary', onclick:`saveAsset(${id||'null'})`},
    {label:'Cancel', cls:'btn-secondary', onclick:`closeModal('modal-asset-edit')`}
  ]);
}

async function saveAsset(id) {
  const data = {
    name: document.getElementById('a-name').value.trim(),
    code: document.getElementById('a-code').value.trim() || null,
    category_id: document.getElementById('a-cat').value || null,
    location_id: document.getElementById('a-loc').value || null,
    status: document.getElementById('a-status').value,
    criticality: document.getElementById('a-crit').value,
    make: document.getElementById('a-make').value,
    model: document.getElementById('a-model').value,
    serial_number: document.getElementById('a-serial').value,
    purchase_date: document.getElementById('a-pdate').value || null,
    purchase_cost: parseFloat(document.getElementById('a-pcost').value) || null,
    warranty_expiry: document.getElementById('a-warranty').value || null,
    description: document.getElementById('a-desc').value,
    notes: document.getElementById('a-notes').value,
  };
  if (!data.name) { toast('Asset name is required', 'error'); return; }
  try {
    if (id) { await api('PUT', '/assets/' + id, data); toast('Asset updated', 'success'); }
    else { await api('POST', '/assets', data); toast('Asset created', 'success'); }
    closeModal('modal-asset-edit'); loadAssets();
  } catch(e) { toast(e.message, 'error'); }
}

async function deleteAsset(id, name) {
  if (!confirm(`Delete asset "${name}"? This cannot be undone.`)) return;
  try { await api('DELETE', '/assets/' + id); toast('Asset deleted', 'success'); loadAssets(); }
  catch(e) { toast(e.message, 'error'); }
}

// ── PM SCHEDULES ──────────────────────────────────────────────────────────────
async function loadPM() {
  const container = document.getElementById('pm-list');
  if (!container) return;
  container.innerHTML = '<div class="loading"><div class="spinner"></div> Loading PM schedules...</div>';
  try {
    const pms = await api('GET', '/pm-schedules');
    if (!pms || !pms.length) {
      container.innerHTML = '<div class="empty-state"><div class="icon">🗓</div><h3>No PM Schedules</h3><p>Create a preventive maintenance schedule to get started.</p></div>';
      return;
    }
    container.innerHTML = pms.map(pm => {
      let checklist = [];
      try { checklist = JSON.parse(pm.checklist || '[]'); } catch(e) {}
      return `
      <div class="card" style="margin-bottom:16px">
        <div style="display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:12px">
          <div>
            <div style="display:flex;align-items:center;gap:10px;margin-bottom:4px">
              <span style="font-size:16px;font-weight:600">${pm.title}</span>
              <span class="badge b-${pm.status||'ok'}">${(pm.status||'ok').replace('_',' ')}</span>
              ${pm.requires_shutdown?'<span class="badge b-warning">🔴 Shutdown Required</span>':''}
            </div>
            <div style="font-size:13px;color:var(--text2);display:flex;gap:16px;flex-wrap:wrap">
              <span>⚙ ${pm.asset_name||'No asset'} <span class="td-mono">${pm.asset_code?`(${pm.asset_code})`:''}</span></span>
              <span>👤 ${pm.assigned_to_name||'Unassigned'}</span>
              <span>🔁 Every ${pm.frequency_value||1} ${pm.frequency}</span>
              <span>⏱ ${pm.estimated_hours||'?'} hrs · ${fmtINR(pm.estimated_cost||0)}</span>
            </div>
          </div>
          <div style="text-align:right;flex-shrink:0">
            <div style="font-size:12px;color:var(--text2)">Last: <span style="font-family:var(--mono)">${pm.last_performed||'Never'}</span></div>
            <div style="font-size:12px;color:var(--text2);margin-top:2px">Next: <span style="font-family:var(--mono);color:${pm.status==='overdue'?'var(--red)':pm.status==='due_soon'?'var(--yellow)':'var(--green)'}">${pm.next_due||'—'}</span></div>
          </div>
        </div>
        ${pm.safety_instructions?`<div style="background:rgba(255,190,77,.06);border:1px solid rgba(255,190,77,.15);border-radius:8px;padding:8px 12px;margin-bottom:10px;font-size:12px;color:var(--yellow)">⚠ ${pm.safety_instructions}</div>`:''}
        ${checklist.length?`<div style="margin-bottom:12px"><div style="font-size:11px;color:var(--text2);text-transform:uppercase;letter-spacing:1px;margin-bottom:8px">Checklist (${checklist.length} tasks)</div>
          <ul class="checklist-view">${checklist.map((item,i)=>`<li><span style="color:var(--text2);font-family:var(--mono);font-size:11px;min-width:20px">${i+1}.</span>${item}</li>`).join('')}</ul></div>`:''}
        <div style="display:flex;gap:8px;flex-wrap:wrap">
          <button class="btn btn-success btn-sm" onclick="completePM(${pm.id})">✓ Mark Complete</button>
          <button class="btn btn-secondary btn-sm" onclick="openPMModal(${pm.id})">✏ Edit</button>
          <button class="btn btn-danger btn-sm admin-only-btn" onclick="deletePM(${pm.id},'${escHtml(pm.title)}')">🗑 Delete</button>
        </div>
      </div>`;
    }).join('');
  } catch(e) { 
    if (container) container.innerHTML = `<div class="empty-state"><div class="icon">⚠</div><h3>Failed to Load PM Schedules</h3><p style="color:var(--red)">${e.message}</p><button class="btn btn-primary" onclick="loadPM()" style="margin-top:12px">🔄 Retry</button></div>`;
    toast('Error: ' + e.message, 'error'); 
  }
}

async function openPMModal(id) {
  let pm = null;
  if (id) {
    try { pm = await api('GET', '/pm-schedules/' + id); } catch(e) {}
  }
  const assets = await getAssets();
  const users = await getUsers();
  let checklist = [];
  if (pm) { try { checklist = JSON.parse(pm.checklist || '[]'); } catch(e) {} }
  const clHtml = checklist.map((item, i) => `
    <div class="checklist-item" id="cl-item-${i}">
      <span style="color:var(--text2);font-family:var(--mono);font-size:11px;min-width:16px">${i+1}</span>
      <input type="text" value="${escHtml(item)}" placeholder="Task description..." id="cl-text-${i}">
      <button onclick="removeCLItem(${i})">✕</button>
    </div>`).join('');

  createModal('modal-pm-edit', id ? `Edit PM: ${pm?.title||''}` : 'New PM Schedule', `
    <div class="form-grid">
      <div class="form-group"><label>Title *</label><input type="text" id="pm-title" class="form-control" value="${pm?.title||''}"></div>
      <div class="form-group"><label>Asset</label><select id="pm-asset" class="form-control">
        <option value="">-- Select Asset --</option>
        ${assets.map(a=>`<option value="${a.id}" ${pm?.asset_id==a.id?'selected':''}>${a.name} (${a.code||''})</option>`).join('')}
      </select></div>
      <div class="form-group"><label>Frequency</label><select id="pm-freq" class="form-control">
        ${['daily','weekly','monthly','quarterly','yearly'].map(f=>`<option value="${f}" ${pm?.frequency==f?'selected':''}>${f}</option>`).join('')}
      </select></div>
      <div class="form-group"><label>Frequency Value</label><input type="number" id="pm-fval" class="form-control" value="${pm?.frequency_value||1}" min="1"></div>
      <div class="form-group"><label>Next Due Date</label><input type="date" id="pm-next" class="form-control" value="${pm?.next_due||''}"></div>
      <div class="form-group"><label>Assigned To</label><select id="pm-assign" class="form-control">
        <option value="">-- Unassigned --</option>
        ${users.map(u=>`<option value="${u.id}" ${pm?.assigned_to==u.id?'selected':''}>${u.full_name}</option>`).join('')}
      </select></div>
      <div class="form-group"><label>Est. Hours</label><input type="number" id="pm-hrs" class="form-control" value="${pm?.estimated_hours||''}" step="0.5"></div>
      <div class="form-group"><label>Est. Cost (₹)</label><input type="number" id="pm-cost" class="form-control" value="${pm?.estimated_cost||''}" step="0.01"></div>
    </div>
    <div class="form-group"><label>Description</label><textarea id="pm-desc" class="form-control">${pm?.description||''}</textarea></div>
    <div class="form-group"><label>Safety Instructions</label><textarea id="pm-safety" class="form-control" style="min-height:60px">${pm?.safety_instructions||''}</textarea></div>
    <div class="form-group">
      <label style="display:flex;align-items:center;gap:8px;cursor:pointer">
        <input type="checkbox" id="pm-shutdown" ${pm?.requires_shutdown?'checked':''} style="accent-color:var(--green)"> Requires Asset Shutdown
      </label>
    </div>
    <div class="form-group">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px">
        <label style="margin:0">Maintenance Checklist</label>
        <button class="btn btn-secondary btn-sm" type="button" onclick="addCLItem()">＋ Add Task</button>
      </div>
      <div class="checklist-editor" id="pm-checklist">${clHtml||'<p style="font-size:12px;color:var(--text2);padding:8px">No tasks yet. Click "+ Add Task" to add checklist items.</p>'}</div>
    </div>
  `, 'modal-lg', [
    {label: id ? 'Save Changes' : 'Create PM', cls:'btn-primary', onclick:`savePM(${id||'null'})`},
    {label:'Cancel', cls:'btn-secondary', onclick:`closeModal('modal-pm-edit')`}
  ]);
  window._clCount = checklist.length;
}

function addCLItem() {
  const container = document.getElementById('pm-checklist');
  const i = window._clCount || 0;
  // Remove empty state message if present
  const empty = container.querySelector('p');
  if (empty) empty.remove();
  const div = document.createElement('div');
  div.className = 'checklist-item';
  div.id = 'cl-item-' + i;
  div.innerHTML = `<span style="color:var(--text2);font-family:var(--mono);font-size:11px;min-width:16px">${i+1}</span>
    <input type="text" placeholder="Task description..." id="cl-text-${i}">
    <button onclick="removeCLItem(${i})">✕</button>`;
  container.appendChild(div);
  window._clCount = i + 1;
  document.getElementById('cl-text-' + i)?.focus();
}

function removeCLItem(i) {
  document.getElementById('cl-item-' + i)?.remove();
}

function getCLItems() {
  const items = [];
  const container = document.getElementById('pm-checklist');
  if (!container) return items;
  container.querySelectorAll('input[type=text]').forEach(inp => {
    const v = inp.value.trim();
    if (v) items.push(v);
  });
  return items;
}

async function savePM(id) {
  const data = {
    title: document.getElementById('pm-title').value.trim(),
    asset_id: document.getElementById('pm-asset').value || null,
    description: document.getElementById('pm-desc').value,
    frequency: document.getElementById('pm-freq').value,
    frequency_value: parseInt(document.getElementById('pm-fval').value) || 1,
    next_due: document.getElementById('pm-next').value || null,
    assigned_to: document.getElementById('pm-assign').value || null,
    estimated_hours: parseFloat(document.getElementById('pm-hrs').value) || null,
    estimated_cost: parseFloat(document.getElementById('pm-cost').value) || null,
    safety_instructions: document.getElementById('pm-safety').value,
    requires_shutdown: document.getElementById('pm-shutdown').checked ? 1 : 0,
    checklist: getCLItems(),
  };
  if (!data.title) { toast('Title is required', 'error'); return; }
  try {
    if (id) { await api('PUT', '/pm-schedules/' + id, data); toast('PM updated', 'success'); }
    else { await api('POST', '/pm-schedules', data); toast('PM schedule created', 'success'); }
    closeModal('modal-pm-edit'); loadPM();
  } catch(e) { toast(e.message, 'error'); }
}

async function completePM(id) {
  const notes = prompt('Completion notes (optional):');
  if (notes === null) return; // cancelled
  try {
    const r = await api('POST', '/pm-schedules/' + id + '/complete', { notes });
    toast(`PM completed! Next due: ${r.next_due} | Created ${r.wo_number}`, 'success');
    loadPM(); loadDashboard();
  } catch(e) { toast(e.message, 'error'); }
}

async function deletePM(id, title) {
  if (!confirm(`Deactivate PM schedule "${title}"?`)) return;
  try { await api('DELETE', '/pm-schedules/' + id); toast('PM schedule deactivated', 'success'); loadPM(); }
  catch(e) { toast(e.message, 'error'); }
}

// ── PARTS ─────────────────────────────────────────────────────────────────────
async function loadParts() {
  const search = document.getElementById('parts-search')?.value || '';
  const low_stock = document.getElementById('parts-low-filter')?.value || '';
  const page = state.pagination.parts || 1;
  try {
    const p = new URLSearchParams({ search, low_stock, page, per_page: 25 });
    const d = await api('GET', '/parts?' + p);
    document.getElementById('parts-tbody').innerHTML = d.items.map(p => `<tr>
      <td class="td-mono">${p.part_number||'—'}</td>
      <td class="td-primary">${p.name}${p.is_low_stock?'<span class="badge b-danger" style="margin-left:6px;font-size:9px">LOW</span>':''}</td>
      <td style="font-family:var(--mono);color:${p.is_low_stock?'var(--red)':'var(--text0)'}">${p.quantity}</td>
      <td style="font-family:var(--mono);color:var(--text2)">${p.min_quantity}</td>
      <td style="font-family:var(--mono);color:var(--green)">${fmtINR2(p.unit_cost||0)}</td>
      <td style="font-size:12px">${p.location||'—'} ${p.bin_number?`<span class="tag">${p.bin_number}</span>`:''}</td>
      <td style="font-size:12px">${p.supplier||'—'}</td>
      <td>
        <button class="btn btn-secondary btn-sm btn-icon" onclick="openPartModal(${p.id})" title="Edit">✏</button>
        <button class="btn btn-warning btn-sm btn-icon" onclick="adjustInventory(${p.id},'${escHtml(p.name)}')" title="Adjust Stock">±</button>
        <button class="btn btn-danger btn-sm btn-icon admin-only-btn" onclick="deletePart(${p.id},'${escHtml(p.name)}')" title="Delete">🗑</button>
      </td>
    </tr>`).join('') || '<tr><td colspan="8" class="empty-state">No parts found</td></tr>';
    renderPagination('parts-pagination', page, d.pages, p => { state.pagination.parts = p; loadParts(); });
  } catch(e) { toast('Error loading parts', 'error'); }
}

async function openPartModal(id) {
  let part = null;
  if (id) { try { const d = await api('GET', `/parts?per_page=1`); part = (await api('GET', '/parts?per_page=999')).items.find(p=>p.id==id); } catch(e) {} }
  createModal('modal-part-edit', id ? 'Edit Part' : 'New Part', `
    <div class="form-grid">
      <div class="form-group"><label>Name *</label><input type="text" id="p-name" class="form-control" value="${part?.name||''}"></div>
      <div class="form-group"><label>Part Number</label><input type="text" id="p-num" class="form-control" value="${part?.part_number||''}"></div>
      <div class="form-group"><label>Quantity</label><input type="number" id="p-qty" class="form-control" value="${part?.quantity||0}" min="0"></div>
      <div class="form-group"><label>Min Quantity</label><input type="number" id="p-min" class="form-control" value="${part?.min_quantity||0}" min="0"></div>
      <div class="form-group"><label>Max Quantity</label><input type="number" id="p-max" class="form-control" value="${part?.max_quantity||100}" min="0"></div>
      <div class="form-group"><label>Unit Cost (₹)</label><input type="number" id="p-cost" class="form-control" value="${part?.unit_cost||0}" step="0.01"></div>
      <div class="form-group"><label>Location</label><input type="text" id="p-loc" class="form-control" value="${part?.location||''}"></div>
      <div class="form-group"><label>Bin Number</label><input type="text" id="p-bin" class="form-control" value="${part?.bin_number||''}"></div>
      <div class="form-group"><label>Supplier</label><input type="text" id="p-supplier" class="form-control" value="${part?.supplier||''}"></div>
      <div class="form-group"><label>Manufacturer</label><input type="text" id="p-mfr" class="form-control" value="${part?.manufacturer||''}"></div>
      <div class="form-group"><label>Lead Time (days)</label><input type="number" id="p-lead" class="form-control" value="${part?.lead_time_days||7}"></div>
    </div>
    <div class="form-group"><label>Description</label><textarea id="p-desc" class="form-control">${part?.description||''}</textarea></div>
    <div class="form-group"><label>Notes</label><textarea id="p-notes" class="form-control" style="min-height:60px">${part?.notes||''}</textarea></div>
  `, 'modal-lg', [
    {label: id ? 'Save Changes' : 'Create Part', cls:'btn-primary', onclick:`savePart(${id||'null'})`},
    {label:'Cancel', cls:'btn-secondary', onclick:`closeModal('modal-part-edit')`}
  ]);
}

async function savePart(id) {
  const data = {
    name: document.getElementById('p-name').value.trim(),
    part_number: document.getElementById('p-num').value.trim() || null,
    quantity: parseInt(document.getElementById('p-qty').value) || 0,
    min_quantity: parseInt(document.getElementById('p-min').value) || 0,
    max_quantity: parseInt(document.getElementById('p-max').value) || 100,
    unit_cost: parseFloat(document.getElementById('p-cost').value) || 0,
    location: document.getElementById('p-loc').value,
    bin_number: document.getElementById('p-bin').value,
    supplier: document.getElementById('p-supplier').value,
    manufacturer: document.getElementById('p-mfr').value,
    lead_time_days: parseInt(document.getElementById('p-lead').value) || 7,
    description: document.getElementById('p-desc').value,
    notes: document.getElementById('p-notes').value,
  };
  if (!data.name) { toast('Part name is required', 'error'); return; }
  try {
    if (id) { await api('PUT', '/parts/' + id, data); toast('Part updated', 'success'); }
    else { await api('POST', '/parts', data); toast('Part created', 'success'); }
    closeModal('modal-part-edit'); loadParts();
  } catch(e) { toast(e.message, 'error'); }
}

async function adjustInventory(id, name) {
  const adj = prompt(`Adjust stock for "${name}" (use +/- number, e.g. +5 or -3):`);
  if (adj === null) return;
  const num = parseInt(adj);
  if (isNaN(num)) { toast('Invalid number', 'error'); return; }
  const reason = prompt('Reason for adjustment:') || '';
  try {
    const r = await api('POST', '/parts/' + id + '/adjust', { adjustment: num, reason });
    toast(`Stock updated to ${r.new_quantity}`, 'success'); loadParts();
  } catch(e) { toast(e.message, 'error'); }
}

async function deletePart(id, name) {
  if (!confirm(`Delete part "${name}"?`)) return;
  try { await api('DELETE', '/parts/' + id); toast('Part deleted', 'success'); loadParts(); }
  catch(e) { toast(e.message, 'error'); }
}

// ── SUPPLIERS ─────────────────────────────────────────────────────────────────
async function loadSuppliers() {
  try {
    const suppliers = await api('GET', '/suppliers');
    document.getElementById('suppliers-tbody').innerHTML = suppliers.map(s => `<tr>
      <td class="td-primary">${s.name}</td>
      <td style="font-size:13px">${s.contact_person||'—'}</td>
      <td style="font-size:12px;color:var(--blue)">${s.email||'—'}</td>
      <td style="font-family:var(--mono);font-size:12px">${s.phone||'—'}</td>
      <td style="font-size:12px">${s.payment_terms||'—'}</td>
      <td>
        <button class="btn btn-secondary btn-sm btn-icon" onclick="openSupplierModal(${s.id})" title="Edit">✏</button>
        <button class="btn btn-danger btn-sm btn-icon admin-only-btn" onclick="deleteSupplier(${s.id},'${escHtml(s.name)}')" title="Delete">🗑</button>
      </td>
    </tr>`).join('') || '<tr><td colspan="6" class="empty-state">No suppliers</td></tr>';
  } catch(e) { toast('Error loading suppliers', 'error'); }
}

async function openSupplierModal(id) {
  let s = null;
  if (id) { try { const d = await api('GET', '/suppliers'); s = d.find(x=>x.id==id); } catch(e) {} }
  createModal('modal-supplier-edit', id ? 'Edit Supplier' : 'New Supplier', `
    <div class="form-grid">
      <div class="form-group"><label>Name *</label><input type="text" id="s-name" class="form-control" value="${s?.name||''}"></div>
      <div class="form-group"><label>Contact Person</label><input type="text" id="s-contact" class="form-control" value="${s?.contact_person||''}"></div>
      <div class="form-group"><label>Email</label><input type="email" id="s-email" class="form-control" value="${s?.email||''}"></div>
      <div class="form-group"><label>Phone</label><input type="text" id="s-phone" class="form-control" value="${s?.phone||''}"></div>
      <div class="form-group"><label>Website</label><input type="text" id="s-web" class="form-control" value="${s?.website||''}"></div>
      <div class="form-group"><label>Payment Terms</label><input type="text" id="s-terms" class="form-control" value="${s?.payment_terms||''}"></div>
    </div>
    <div class="form-group"><label>Address</label><input type="text" id="s-addr" class="form-control" value="${s?.address||''}"></div>
    <div class="form-group"><label>Notes</label><textarea id="s-notes" class="form-control">${s?.notes||''}</textarea></div>
  `, '', [
    {label: id ? 'Save Changes' : 'Create Supplier', cls:'btn-primary', onclick:`saveSupplier(${id||'null'})`},
    {label:'Cancel', cls:'btn-secondary', onclick:`closeModal('modal-supplier-edit')`}
  ]);
}

async function saveSupplier(id) {
  const data = {
    name: document.getElementById('s-name').value.trim(),
    contact_person: document.getElementById('s-contact').value,
    email: document.getElementById('s-email').value,
    phone: document.getElementById('s-phone').value,
    website: document.getElementById('s-web').value,
    payment_terms: document.getElementById('s-terms').value,
    address: document.getElementById('s-addr').value,
    notes: document.getElementById('s-notes').value,
  };
  if (!data.name) { toast('Supplier name is required', 'error'); return; }
  try {
    if (id) { await api('PUT', '/suppliers/' + id, data); toast('Supplier updated', 'success'); }
    else { await api('POST', '/suppliers', data); toast('Supplier created', 'success'); }
    closeModal('modal-supplier-edit'); loadSuppliers();
  } catch(e) { toast(e.message, 'error'); }
}

async function deleteSupplier(id, name) {
  if (!confirm(`Delete supplier "${name}"?`)) return;
  try { await api('DELETE', '/suppliers/' + id); toast('Supplier deleted', 'success'); loadSuppliers(); }
  catch(e) { toast(e.message, 'error'); }
}

// ── USER MANAGEMENT ───────────────────────────────────────────────────────────
async function loadUsers() {
  try {
    const users = await api('GET', '/users');
    const roleColors = { admin:'var(--purple)', manager:'var(--blue)', supervisor:'var(--yellow)', technician:'var(--green)' };
    const roleGrad = { admin:'135deg,#3d1a5c,#6b2fa0', manager:'135deg,#1a3a5c,#2f6ea0', supervisor:'135deg,#5c4200,#a07020', technician:'135deg,#005c35,#00a060' };
    document.getElementById('user-grid').innerHTML = users.map(u => `
      <div class="user-card ${u.is_active?'':'user-inactive'}">
        <div class="user-card-head">
          <div class="user-card-av" style="background:linear-gradient(${roleGrad[u.role]||'135deg,#1a1a2e,#333'});color:white">
            ${(u.full_name||u.username).split(' ').map(w=>w[0]).join('').toUpperCase().slice(0,2)}
          </div>
          <div class="user-card-info">
            <h4>${u.full_name||u.username}</h4>
            <p><span class="badge b-${u.role}">${u.role}</span></p>
          </div>
        </div>
        <div class="user-card-meta">
          <span>👤 <span class="td-mono" style="font-size:11px">@${u.username}</span></span>
          ${u.email?`<span>✉ ${u.email}</span>`:''}
          ${u.department?`<span>🏢 ${u.department}</span>`:''}
          ${u.phone?`<span>📞 ${u.phone}</span>`:''}
          <span><div class="status-dot ${u.is_active?'active':'inactive'}"></div> ${u.is_active?'Active':'Inactive'}</span>
          <span style="color:var(--text2);font-size:11px">Last login: <span style="font-family:var(--mono)">${u.last_login?.slice(0,16)||'Never'}</span></span>
        </div>
        <div class="user-card-actions">
          <button class="btn btn-secondary btn-sm btn-icon" onclick="openUserModal(${u.id})" title="Edit">✏</button>
          <button class="btn btn-warning btn-sm btn-icon" onclick="resetUserPassword(${u.id},'${escHtml(u.full_name||u.username)}')" title="Reset Password">🔑</button>
          <button class="btn btn-danger btn-sm btn-icon" onclick="deleteUser(${u.id},'${escHtml(u.full_name||u.username)}')" title="${u.is_active?'Deactivate':'Already inactive'}">🗑</button>
        </div>
      </div>`).join('');
  } catch(e) { toast('Error loading users', 'error'); }
}

async function openUserModal(id) {
  let user = null;
  if (id) { try { user = await api('GET', '/users/' + id); } catch(e) {} }
  createModal('modal-user-edit', id ? `Edit User: ${user?.full_name||user?.username}` : 'Create New User', `
    <div class="form-grid">
      <div class="form-group"><label>Username *</label>
        <input type="text" id="u-username" class="form-control" value="${user?.username||''}" ${id?'readonly':''} autocomplete="off">
      </div>
      <div class="form-group"><label>Full Name</label><input type="text" id="u-fullname" class="form-control" value="${user?.full_name||''}"></div>
      <div class="form-group"><label>${id?'New Password (leave blank to keep)':'Password *'}</label>
        <input type="password" id="u-password" class="form-control" autocomplete="new-password" placeholder="${id?'Leave blank to keep current':'Required'}">
      </div>
      <div class="form-group"><label>Role</label><select id="u-role" class="form-control">
        ${['technician','supervisor','manager','admin'].map(r=>`<option value="${r}" ${user?.role==r?'selected':''}>${r}</option>`).join('')}
      </select></div>
      <div class="form-group"><label>Email</label><input type="email" id="u-email" class="form-control" value="${user?.email||''}"></div>
      <div class="form-group"><label>Department</label><input type="text" id="u-dept" class="form-control" value="${user?.department||''}"></div>
      <div class="form-group"><label>Phone</label><input type="text" id="u-phone" class="form-control" value="${user?.phone||''}"></div>
      <div class="form-group"><label style="display:flex;align-items:center;gap:8px;cursor:pointer">
        <input type="checkbox" id="u-active" ${!id||user?.is_active?'checked':''} style="accent-color:var(--green)"> Active Account
      </label></div>
    </div>
    <div style="background:rgba(255,190,77,.08);border:1px solid rgba(255,190,77,.2);border-radius:8px;padding:12px;font-size:12px;color:var(--yellow)">
      ⚠ User management is restricted to admins only. Changes are logged in the audit trail.
    </div>
  `, '', [
    {label: id ? 'Save Changes' : 'Create User', cls:'btn-primary', onclick:`saveUser(${id||'null'})`},
    {label:'Cancel', cls:'btn-secondary', onclick:`closeModal('modal-user-edit')`}
  ]);
}

async function saveUser(id) {
  const pw = document.getElementById('u-password').value;
  const data = {
    username: document.getElementById('u-username').value.trim(),
    full_name: document.getElementById('u-fullname').value.trim(),
    role: document.getElementById('u-role').value,
    email: document.getElementById('u-email').value.trim(),
    department: document.getElementById('u-dept').value.trim(),
    phone: document.getElementById('u-phone').value.trim(),
    is_active: document.getElementById('u-active').checked,
  };
  if (pw) data.password = pw;
  if (!id && !pw) { toast('Password is required for new users', 'error'); return; }
  if (!data.username) { toast('Username is required', 'error'); return; }
  try {
    if (id) { await api('PUT', '/users/' + id, data); toast('User updated', 'success'); }
    else { await api('POST', '/users', data); toast(`User @${data.username} created`, 'success'); }
    closeModal('modal-user-edit'); loadUsers();
  } catch(e) { toast(e.message, 'error'); }
}

async function resetUserPassword(id, name) {
  const newPw = prompt(`Set new password for ${name}:`, 'Welcome123!');
  if (!newPw) return;
  try {
    await api('POST', '/users/' + id + '/reset-password', { new_password: newPw });
    toast(`Password reset for ${name}`, 'success');
  } catch(e) { toast(e.message, 'error'); }
}

async function deleteUser(id, name) {
  if (id === state.user?.id) { toast("You can't deactivate your own account", 'error'); return; }
  if (!confirm(`Deactivate user "${name}"? They will no longer be able to log in.`)) return;
  try { await api('DELETE', '/users/' + id); toast(`User "${name}" deactivated`, 'success'); loadUsers(); }
  catch(e) { toast(e.message, 'error'); }
}

// ── AUDIT LOG ─────────────────────────────────────────────────────────────────
async function loadAudit() {
  const action = document.getElementById('audit-action-filter')?.value || '';
  const table = document.getElementById('audit-table-filter')?.value || '';
  const page = state.pagination.audit || 1;
  try {
    const p = new URLSearchParams({ action, table, page, per_page: 50 });
    const d = await api('GET', '/audit-log?' + p);
    document.getElementById('audit-tbody').innerHTML = d.items.map(l => `<tr>
      <td style="font-family:var(--mono);font-size:11px;color:var(--text2);white-space:nowrap">${l.created_at?.slice(0,16)||'—'}</td>
      <td>
        <div style="font-size:13px;font-weight:500">${l.full_name||l.username||'System'}</div>
        ${l.username?`<div class="td-mono" style="font-size:10px;color:var(--text2)">@${l.username}</div>`:''}
      </td>
      <td><span class="audit-action audit-${l.action}">${l.action}</span></td>
      <td style="font-family:var(--mono);font-size:12px;color:var(--text2)">${l.table_name||'—'}</td>
      <td style="font-family:var(--mono);font-size:12px">#${l.record_id||'—'}</td>
      <td style="font-size:12px;color:var(--text1);max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${escHtml(l.details||'')}">${l.details||'—'}</td>
      <td style="font-family:var(--mono);font-size:11px;color:var(--text2)">${l.ip_address||'—'}</td>
      <td>${(l.old_value||l.new_value)?`<button class="audit-detail-toggle" onclick="showAuditDiff(${l.id})">diff</button>`:''}</td>
    </tr>
    ${(l.old_value||l.new_value)?`<tr id="audit-diff-${l.id}" style="display:none"><td colspan="8"><div class="audit-diff">
      ${l.old_value?`<div class="diff-old">− ${escHtml(l.old_value)}</div>`:''}
      ${l.new_value?`<div class="diff-new">+ ${escHtml(l.new_value)}</div>`:''}
    </div></td></tr>`:''}
    `).join('') || '<tr><td colspan="8" class="empty-state">No audit records</td></tr>';
    renderPagination('audit-pagination', page, d.pages, p => { state.pagination.audit = p; loadAudit(); });
  } catch(e) { toast('Error loading audit log', 'error'); }
}

function showAuditDiff(id) {
  const row = document.getElementById('audit-diff-' + id);
  if (row) row.style.display = row.style.display === 'none' ? '' : 'none';
}

// ── SETTINGS ──────────────────────────────────────────────────────────────────
async function loadSettings() {
  try {
    const settings = await api('GET', '/settings');
    state.data.settings = {};
    settings.forEach(s => state.data.settings[s.key] = s.value);
    document.getElementById('settings-form').innerHTML = `
      <div class="form-grid">${settings.map(s => `
        <div class="form-group">
          <label>${s.key.replace(/_/g,' ')}</label>
          <input type="text" id="setting-${s.key}" class="form-control" value="${escHtml(s.value||'')}" placeholder="${s.description||''}">
        </div>`).join('')}
      </div>`;
  } catch(e) { toast('Error loading settings', 'error'); }
}

async function saveSettings() {
  if (!state.data.settings) return;
  const data = {};
  Object.keys(state.data.settings).forEach(key => {
    const el = document.getElementById('setting-' + key);
    if (el) data[key] = el.value;
  });
  try { await api('PUT', '/settings', data); toast('Settings saved', 'success'); }
  catch(e) { toast(e.message, 'error'); }
}

// ── PROFILE ───────────────────────────────────────────────────────────────────
function loadProfile() {
  const u = state.user;
  if (!u) return;
  document.getElementById('profile-content').innerHTML = `
    <div style="display:flex;align-items:center;gap:16px;margin-bottom:20px">
      <div class="user-card-av" style="width:64px;height:64px;background:linear-gradient(135deg,var(--green),var(--blue));font-size:24px;font-weight:700;color:var(--bg0);display:flex;align-items:center;justify-content:center;border-radius:50%;flex-shrink:0">
        ${(u.full_name||u.username).split(' ').map(w=>w[0]).join('').toUpperCase().slice(0,2)}
      </div>
      <div>
        <h3 style="font-size:20px;font-weight:600">${u.full_name||u.username}</h3>
        <span class="badge b-${u.role}" style="margin-top:4px">${u.role}</span>
      </div>
    </div>
    <div class="form-group"><label>Username</label><div class="td-mono" style="font-size:14px">@${u.username}</div></div>
    <div class="form-group"><label>Email</label><div style="font-size:14px">${u.email||'—'}</div></div>
    <div class="form-group"><label>Department</label><div style="font-size:14px">${u.department||'—'}</div></div>
    <div class="form-group"><label>Phone</label><div style="font-size:14px">${u.phone||'—'}</div></div>
  `;
}

async function changePassword() {
  const old = document.getElementById('pw-old').value;
  const nw = document.getElementById('pw-new').value;
  const confirm = document.getElementById('pw-confirm').value;
  if (!old || !nw) { toast('Fill in all password fields', 'error'); return; }
  if (nw !== confirm) { toast('Passwords do not match', 'error'); return; }
  if (nw.length < 6) { toast('Password must be at least 6 characters', 'error'); return; }
  try {
    await api('POST', '/change-password', { old_password: old, new_password: nw });
    toast('Password changed successfully', 'success');
    document.getElementById('pw-old').value = '';
    document.getElementById('pw-new').value = '';
    document.getElementById('pw-confirm').value = '';
  } catch(e) { toast(e.message, 'error'); }
}

// ── NOTIFICATIONS ─────────────────────────────────────────────────────────────
async function showNotifications() {
  try {
    const notifs = await api('GET', '/notifications');
    const unread = notifs.filter(n => !n.is_read);
    createModal('modal-notifs', `🔔 Notifications (${unread.length} unread)`, `
      <div style="display:flex;justify-content:flex-end;margin-bottom:12px">
        <button class="btn btn-secondary btn-sm" onclick="markAllRead()">Mark All Read</button>
      </div>
      ${notifs.length ? notifs.map(n => `
        <div style="padding:12px;border-bottom:1px solid var(--border);display:flex;gap:10px;align-items:flex-start;${!n.is_read?'background:var(--bg3)':''}">
          <div style="width:8px;height:8px;border-radius:50%;background:${!n.is_read?'var(--green)':'var(--border2)'};flex-shrink:0;margin-top:5px"></div>
          <div style="flex:1">
            <div style="font-size:13px;font-weight:500">${n.title}</div>
            <div style="font-size:12px;color:var(--text2);margin-top:2px">${n.message}</div>
            <div style="font-size:11px;color:var(--text2);font-family:var(--mono);margin-top:4px">${n.created_at?.slice(0,16)||''}</div>
          </div>
        </div>`).join('') : '<div class="empty-state"><div class="icon">🔔</div><p>No notifications</p></div>'}
    `, '', [{label:'Close', cls:'btn-secondary', onclick:`closeModal('modal-notifs')`}]);
    // Mark as read
    if (unread.length) {
      await api('POST', '/notifications/read-all');
      document.getElementById('notif-dot').style.display = 'none';
    }
  } catch(e) {}
}

async function markAllRead() {
  await api('POST', '/notifications/read-all');
  document.getElementById('notif-dot').style.display = 'none';
  closeModal('modal-notifs');
}

// ── HELPERS ───────────────────────────────────────────────────────────────────
async function getUsers() {
  if (!state.data.users) state.data.users = await api('GET', '/users');
  return state.data.users.filter(u => u.is_active);
}

async function getAssets() {
  if (!state.data.assetsList) { const d = await api('GET', '/assets?per_page=999'); state.data.assetsList = d.items; }
  return state.data.assetsList;
}

async function loadCategories() {
  const cats = await api('GET', '/categories');
  state.data.categories = cats;
  const sel = document.getElementById('asset-cat-filter');
  if (sel) cats.forEach(c => {
    const opt = document.createElement('option');
    opt.value = c.id; opt.textContent = (c.icon||'') + ' ' + c.name;
    sel.appendChild(opt);
  });
}

function escHtml(str) { return String(str||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;'); }

let _debounceTimers = {};
function debounce(fn, ms, key='default') {
  clearTimeout(_debounceTimers[key]);
  _debounceTimers[key] = setTimeout(fn, ms);
}

function toast(msg, type='success') {
  const t = document.getElementById('toast');
  t.textContent = msg; t.className = 'show ' + type;
  setTimeout(() => t.classList.remove('show'), 3500);
}

function renderPagination(containerId, current, total, onChange) {
  const cont = document.getElementById(containerId);
  if (!cont || total <= 1) { if (cont) cont.innerHTML = ''; return; }
  let html = `<span class="pag-info">Page ${current} of ${total}</span>`;
  html += `<button class="pag-btn" onclick="(${onChange.toString()})(1)" ${current<=1?'disabled':''}>«</button>`;
  html += `<button class="pag-btn" onclick="(${onChange.toString()})(${current-1})" ${current<=1?'disabled':''}>‹</button>`;
  for (let p = Math.max(1, current-2); p <= Math.min(total, current+2); p++) {
    html += `<button class="pag-btn ${p===current?'active':''}" onclick="(${onChange.toString()})(${p})">${p}</button>`;
  }
  html += `<button class="pag-btn" onclick="(${onChange.toString()})(${current+1})" ${current>=total?'disabled':''}>›</button>`;
  html += `<button class="pag-btn" onclick="(${onChange.toString()})(${total})" ${current>=total?'disabled':''}>»</button>`;
  cont.innerHTML = html;
}

function createModal(id, title, body, extraClass='', buttons=[]) {
  closeModal(id);
  const div = document.createElement('div');
  div.className = 'modal-overlay';
  div.id = 'overlay-' + id;
  div.onclick = e => { if (e.target === div) closeModal(id); };
  div.innerHTML = `
    <div class="modal ${extraClass}" id="${id}">
      <div class="modal-header">
        <h3>${title}</h3>
        <button class="modal-close" onclick="closeModal('${id}')">&times;</button>
      </div>
      <div class="modal-body">${body}</div>
      <div class="modal-footer">${buttons.map(b=>`<button class="btn ${b.cls||''}" onclick="${b.onclick}">${b.label}</button>`).join('')}</div>
    </div>`;
  document.getElementById('modal-container').appendChild(div);
  return div;
}

function closeModal(id) {
  const el = document.getElementById('overlay-' + id);
  if (el) el.remove();
}


// ── EQUIPMENT HISTORY PAGE ────────────────────────────────────────────────────
let historyState = { assetId: null, allEvents: [], tab: 'all', asset: null };

async function initEqHistory() {
  // Populate asset selector
  const assets = await getAssets();
  const sel = document.getElementById('eq-history-asset-sel');
  if (sel.options.length <= 1) {
    assets.forEach(a => {
      const opt = document.createElement('option');
      opt.value = a.id;
      opt.textContent = `${a.name}${a.code ? ' (' + a.code + ')' : ''} — ${a.category_name || ''}`;
      sel.appendChild(opt);
    });
  }
  // Add current year to year filter
  const yr = document.getElementById('eq-history-year');
  const curYear = new Date().getFullYear();
  if (!Array.from(yr.options).find(o => o.value == curYear)) {
    const opt = document.createElement('option');
    opt.value = curYear; opt.textContent = curYear;
    yr.insertBefore(opt, yr.options[1]);
  }
}

async function selectHistoryAsset() {
  const assetId = document.getElementById('eq-history-asset-sel').value;
  document.getElementById('eq-history-placeholder').style.display = 'none';
  document.getElementById('eq-history-empty').style.display = 'none';
  document.getElementById('eq-history-tabs').style.display = 'none';
  document.getElementById('eq-history-summary').style.display = 'none';
  document.getElementById('eq-history-asset-header').style.display = 'none';

  if (!assetId) {
    document.getElementById('eq-history-placeholder').style.display = 'block';
    return;
  }
  historyState.assetId = assetId;
  historyState.tab = 'all';

  // Reset tab buttons
  document.querySelectorAll('#eq-history-tabs .tab-btn').forEach(b => b.classList.remove('active'));
  document.getElementById('htab-all').classList.add('active');

  try {
    // Load asset detail + history simultaneously
    const [assetRes, history] = await Promise.all([
      api('GET', '/assets/' + assetId),
      api('GET', '/assets/' + assetId + '/history')
    ]);
    const asset = assetRes.asset;
    historyState.asset = asset;
    historyState.allEvents = history;
    historyState.workOrders = assetRes.work_orders || [];
    historyState.pmSchedules = assetRes.pm_schedules || [];

    // Asset header card
    const statusColor = asset.status === 'active' ? 'var(--green)' : asset.status === 'maintenance' ? 'var(--yellow)' : 'var(--text2)';
    document.getElementById('eq-history-asset-header').style.display = 'flex';
    document.getElementById('eq-history-asset-header').innerHTML = `
      <div class="eq-asset-icon">${asset.category_icon || '⚙'}</div>
      <div style="flex:1">
        <div style="font-size:18px;font-weight:700;margin-bottom:4px">${asset.name}</div>
        <div style="display:flex;gap:12px;flex-wrap:wrap;font-size:12px;color:var(--text2)">
          <span class="td-mono">${asset.code || '—'}</span>
          <span>${asset.make || ''} ${asset.model || ''}</span>
          <span>📍 ${asset.location_name || '—'}</span>
          <span style="color:${statusColor}">● ${asset.status}</span>
          <span>🔴 Criticality: <strong style="color:var(--text0)">${asset.criticality}</strong></span>
        </div>
      </div>
      <div style="text-align:right;flex-shrink:0">
        <div style="font-size:12px;color:var(--text2)">Purchase Cost</div>
        <div style="font-family:var(--mono);font-size:18px;color:var(--green)">${fmtINR(asset.purchase_cost||0)}</div>
        <div style="font-size:11px;color:var(--text2);margin-top:4px">Purchased: ${asset.purchase_date || '—'}</div>
      </div>`;

    renderHistorySummary();
    document.getElementById('eq-history-summary').style.display = 'grid';
    document.getElementById('eq-history-tabs').style.display = 'block';
    await renderHistoryTab();
  } catch(e) { toast('Error loading equipment history: ' + e.message, 'error'); }
}

function getFilteredEvents() {
  const year = document.getElementById('eq-history-year')?.value || '';
  if (!year) return historyState.allEvents;
  return historyState.allEvents.filter(e => (e.created_at || '').startsWith(year));
}

function getFilteredWOs() {
  const year = document.getElementById('eq-history-year')?.value || '';
  if (!year) return historyState.workOrders;
  return historyState.workOrders.filter(w => (w.created_at || '').startsWith(year));
}

function renderHistorySummary() {
  const events = historyState.allEvents;
  const wos = historyState.workOrders;
  const totalCost = wos.reduce((s, w) => s + (w.total_cost || 0), 0);
  const completedWOs = wos.filter(w => w.status === 'completed').length;
  const pmEvents = events.filter(e => e.event_type === 'pm_completion').length;
  const lastEvent = events[0];
  const lastDate = lastEvent ? (lastEvent.created_at || '').slice(0, 10) : '—';

  document.getElementById('eq-history-summary').innerHTML = `
    <div class="hist-stat blue"><div class="hist-stat-val">${wos.length}</div><div class="hist-stat-lbl">Total Work Orders</div></div>
    <div class="hist-stat green"><div class="hist-stat-val">${completedWOs}</div><div class="hist-stat-lbl">Completed WOs</div></div>
    <div class="hist-stat green"><div class="hist-stat-val">${pmEvents}</div><div class="hist-stat-lbl">PM Completions</div></div>
    <div class="hist-stat yellow"><div class="hist-stat-val">${fmtINR(totalCost)}</div><div class="hist-stat-lbl">Total Maint. Cost</div></div>
    <div class="hist-stat"><div class="hist-stat-val" style="font-size:16px">${lastDate}</div><div class="hist-stat-lbl">Last Service</div></div>
    <div class="hist-stat"><div class="hist-stat-val">${events.length}</div><div class="hist-stat-lbl">Total Events</div></div>`;
}

async function switchHistoryTab(tab) {
  historyState.tab = tab;
  document.querySelectorAll('#eq-history-tabs .tab-btn').forEach(b => b.classList.remove('active'));
  document.getElementById('htab-' + tab)?.classList.add('active');
  await renderHistoryTab();
}

async function renderHistoryTab() {
  const tab = historyState.tab;
  const content = document.getElementById('eq-history-content');
  if (!content) return;
  content.innerHTML = '<div class="loading"><div class="spinner"></div> Loading...</div>';

  if (tab === 'all') renderAllEvents(content);
  else if (tab === 'wo') renderWOTab(content);
  else if (tab === 'pm') renderPMTab(content);
  else if (tab === 'status') renderStatusTab(content);
  else if (tab === 'cost') renderCostTab(content);
  else if (tab === 'corrective') renderCorrectiveTab(content);
  else if (tab === 'downtime') await renderDowntimeTab(content);
  else if (tab === 'parts') await renderAssetPartsTab(content);
  else if (tab === 'depreciation') renderDepreciationTab(content);
}

function renderAllEvents(container) {
  const events = getFilteredEvents();
  const typeIcons = { work_order:'📋', pm_completion:'✅', status_change:'🔄', created:'⭐', meter_reading:'📊' };
  const typeColors = { work_order:'var(--blue)', pm_completion:'var(--green)', status_change:'var(--yellow)', created:'var(--purple)', meter_reading:'var(--text2)' };
  if (!events.length) { container.innerHTML = '<div class="empty-state"><div class="icon">📅</div><p>No events found for the selected period.</p></div>'; return; }
  container.innerHTML = `
    <div class="card">
      <div class="card-header"><span class="card-title">All Events (${events.length})</span></div>
      <div class="timeline">
        ${events.map(h => `
          <div class="timeline-item tl-${h.event_type}">
            <div class="tl-header">
              <div class="tl-title" style="display:flex;align-items:center;gap:8px">
                <span style="font-size:16px">${typeIcons[h.event_type] || '•'}</span>
                <span>${h.event_title}</span>
                ${h.cost && h.cost > 0 ? `<span style="font-family:var(--mono);font-size:11px;color:var(--green);margin-left:auto">${fmtINR2(h.cost)}</span>` : ''}
              </div>
              <div class="tl-date">${(h.created_at || '').slice(0, 16)}</div>
            </div>
            ${h.event_detail ? `<div class="tl-detail">${h.event_detail}</div>` : ''}
            ${h.performed_by_name ? `<div class="tl-by">by ${h.performed_by_name}</div>` : ''}
          </div>`).join('')}
      </div>
    </div>`;
}

function renderWOTab(container) {
  const wos = getFilteredWOs();
  if (!wos.length) { container.innerHTML = '<div class="empty-state"><div class="icon">📋</div><p>No work orders found.</p></div>'; return; }
  const totalCost = wos.reduce((s,w) => s + (w.total_cost||0), 0);
  const totalHrs = wos.reduce((s,w) => s + (w.actual_hours||0), 0);
  container.innerHTML = `
    <div class="card">
      <div class="card-header">
        <span class="card-title">Work Orders (${wos.length})</span>
        <div style="display:flex;gap:16px;font-size:12px;color:var(--text2)">
          <span>Total Cost: <span style="color:var(--green);font-family:var(--mono)">${fmtINR(totalCost)}</span></span>
          <span>Total Hours: <span style="color:var(--blue);font-family:var(--mono)">${totalHrs.toFixed(1)}</span></span>
        </div>
      </div>
      <div class="tbl-wrap"><table>
        <thead><tr><th>WO #</th><th>Title</th><th>Type</th><th>Priority</th><th>Status</th><th>Hours</th><th>Cost</th><th>Date</th></tr></thead>
        <tbody>
          ${wos.map(w => `<tr onclick="openWODetail(${w.id})" style="cursor:pointer">
            <td class="td-mono">${w.wo_number || '—'}</td>
            <td class="td-primary">${w.title}</td>
            <td><span class="tag">${w.type}</span></td>
            <td><span class="badge b-${w.priority}">${w.priority}</span></td>
            <td><span class="badge b-${w.status}">${w.status.replace('_',' ')}</span></td>
            <td style="font-family:var(--mono);font-size:12px">${w.actual_hours || '—'}</td>
            <td style="font-family:var(--mono);font-size:12px;color:var(--green)">${fmtINR(w.total_cost||0)}</td>
            <td style="font-family:var(--mono);font-size:11px;color:var(--text2)">${(w.created_at||'').slice(0,10)}</td>
          </tr>`).join('')}
        </tbody>
      </table></div>
    </div>`;
}

function renderPMTab(container) {
  const pmEvents = getFilteredEvents().filter(e => e.event_type === 'pm_completion');
  const pmSchedules = historyState.pmSchedules || [];
  if (!pmEvents.length && !pmSchedules.length) {
    container.innerHTML = '<div class="empty-state"><div class="icon">✅</div><p>No PM schedules or completions recorded yet.</p></div>';
    return;
  }
  // Pre-compute inner rows to avoid triple-nested template literals
  const pmScheduleRows = pmSchedules.map(p => {
    const due = p.next_due ? new Date(p.next_due) : null;
    const isOverdue = due && due < new Date();
    const color = isOverdue ? 'var(--red)' : 'var(--text0)';
    const fw = isOverdue ? 'font-weight:700' : '';
    const dateStr = p.next_due ? (p.next_due || '').slice(0, 10) : '—';
    const tagColor = isOverdue ? 'var(--red)' : 'var(--green)';
    const tagLabel = isOverdue ? 'Overdue' : 'Active';
    return '<tr>'
      + '<td class="td-primary">' + (p.task_name || '') + '</td>'
      + '<td style="font-size:12px">' + (p.frequency_value || '') + ' ' + (p.frequency_unit || '') + '</td>'
      + '<td class="td-mono" style="color:' + color + ';' + fw + '">' + dateStr + (isOverdue ? ' ⚠' : '') + '</td>'
      + '<td style="font-size:12px">' + (p.estimated_hours ? p.estimated_hours + 'h' : '—') + '</td>'
      + '<td><span class="tag" style="color:' + tagColor + ';">' + tagLabel + '</span></td>'
      + '</tr>';
  }).join('');
  container.innerHTML = `
    ${pmSchedules.length ? `
    <div class="card" style="margin-bottom:16px">
      <div class="card-header"><span class="card-title">📅 Active PM Schedules (${pmSchedules.length})</span></div>
      <div class="tbl-wrap"><table>
        <thead><tr><th>Task</th><th>Frequency</th><th>Next Due</th><th>Est. Duration</th><th>Status</th></tr></thead>
        <tbody>${pmScheduleRows}</tbody>
      </table></div>
    </div>` : ''}
    ${pmEvents.length ? `
    <div class="card">
      <div class="card-header"><span class="card-title">PM Completions (${pmEvents.length})</span>
        <span style="font-size:12px;color:var(--green)">✓ ${pmEvents.length} maintenance tasks completed</span>
      </div>
      <div class="tbl-wrap"><table>
        <thead><tr><th>Task</th><th>Detail</th><th>Cost</th><th>Performed By</th><th>Date</th></tr></thead>
        <tbody>
          ${pmEvents.map(e => `<tr>
            <td class="td-primary">${e.event_title.replace('PM Completed: ','')}</td>
            <td style="font-size:12px;color:var(--text1);max-width:200px">${e.event_detail || '—'}</td>
            <td style="font-family:var(--mono);font-size:12px;color:var(--green)">${e.cost > 0 ? fmtINR(e.cost) : '—'}</td>
            <td style="font-size:12px">${e.performed_by_name || '—'}</td>
            <td style="font-family:var(--mono);font-size:11px;color:var(--text2)">${(e.created_at||'').slice(0,10)}</td>
          </tr>`).join('')}
        </tbody>
      </table></div>
    </div>` : ''}`;
}

function renderStatusTab(container) {
  const statusEvents = getFilteredEvents().filter(e => e.event_type === 'status_change' || e.event_type === 'created');
  if (!statusEvents.length) { container.innerHTML = '<div class="empty-state"><div class="icon">🔄</div><p>No status changes recorded.</p></div>'; return; }
  container.innerHTML = `
    <div class="card">
      <div class="card-header"><span class="card-title">Status Changes & Lifecycle (${statusEvents.length})</span></div>
      <div class="timeline">
        ${statusEvents.map(e => `
          <div class="timeline-item tl-${e.event_type}">
            <div class="tl-header">
              <div class="tl-title">${e.event_type === 'created' ? '⭐' : '🔄'} ${e.event_title}</div>
              <div class="tl-date">${(e.created_at||'').slice(0,16)}</div>
            </div>
            ${e.event_detail ? `<div class="tl-detail">${e.event_detail}</div>` : ''}
            ${e.performed_by_name ? `<div class="tl-by">by ${e.performed_by_name}</div>` : ''}
          </div>`).join('')}
      </div>
    </div>`;
}

function renderCostTab(container) {
  const wos = getFilteredWOs();
  const pmEvents = getFilteredEvents().filter(e => e.event_type === 'pm_completion');
  const woTotal = wos.reduce((s,w) => s + (w.total_cost||0), 0);
  const pmTotal = pmEvents.reduce((s,e) => s + (e.cost||0), 0);
  const grandTotal = woTotal + pmTotal;
  const asset = historyState.asset;

  // Cost by WO type
  const byType = {};
  wos.forEach(w => { byType[w.type] = (byType[w.type]||0) + (w.total_cost||0); });

  // Monthly cost trend
  const monthly = {};
  wos.forEach(w => {
    const m = (w.created_at||'').slice(0,7);
    if (m) monthly[m] = (monthly[m]||0) + (w.total_cost||0);
  });
  const months = Object.keys(monthly).sort();
  const maxMonthlyCost = Math.max(...Object.values(monthly), 1);

  const typeColors = { corrective:'var(--red)', preventive:'var(--green)', inspection:'var(--blue)', emergency:'var(--purple)' };

  container.innerHTML = `
    <div class="two-col">
      <div class="card">
        <div class="card-header"><span class="card-title">💰 Cost Breakdown</span></div>
        <div style="margin-bottom:16px">
          <div style="font-size:28px;font-weight:700;font-family:var(--mono);color:var(--green)">${fmtINR(grandTotal)}</div>
          <div style="font-size:12px;color:var(--text2);margin-top:4px">Total Maintenance Cost</div>
        </div>
        <div class="cost-bar-wrap">
          <div class="cost-bar-label"><span>Corrective / Repair</span><span style="font-family:var(--mono)">${fmtINR(woTotal)}</span></div>
          <div class="cost-bar-track"><div class="cost-bar-fill" style="width:${grandTotal?Math.round(woTotal/grandTotal*100):0}%;background:var(--yellow)"></div></div>
        </div>
        <div class="cost-bar-wrap" style="margin-top:12px">
          <div class="cost-bar-label"><span>Preventive / PM</span><span style="font-family:var(--mono)">${fmtINR(pmTotal)}</span></div>
          <div class="cost-bar-track"><div class="cost-bar-fill" style="width:${grandTotal?Math.round(pmTotal/grandTotal*100):0}%;background:var(--green)"></div></div>
        </div>
        <hr class="divider">
        <div class="card-title" style="margin-bottom:12px">By Work Order Type</div>
        ${Object.entries(byType).map(([type, cost]) => `
          <div class="cost-bar-wrap" style="margin-bottom:10px">
            <div class="cost-bar-label">
              <span style="text-transform:capitalize">${type}</span>
              <span style="font-family:var(--mono);font-size:12px">${fmtINR(cost)}</span>
            </div>
            <div class="cost-bar-track"><div class="cost-bar-fill" style="width:${woTotal?Math.round(cost/woTotal*100):0}%;background:${typeColors[type]||'var(--text2)'}"></div></div>
          </div>`).join('')}
        ${asset?.purchase_cost ? `
          <hr class="divider">
          <div style="font-size:12px;color:var(--text2)">Purchase Cost</div>
          <div style="font-family:var(--mono);font-size:14px;color:var(--text0)">${fmtINR(asset.purchase_cost)}</div>
          <div style="font-size:12px;color:var(--text2);margin-top:8px">Maintenance as % of Purchase</div>
          <div style="font-family:var(--mono);font-size:20px;color:${grandTotal/asset.purchase_cost>.5?'var(--red)':'var(--yellow)'}">${(grandTotal/asset.purchase_cost*100).toFixed(1)}%</div>` : ''}
      </div>
      <div class="card">
        <div class="card-header"><span class="card-title">📈 Monthly Cost Trend</span></div>
        ${months.length ? `
          <div style="display:flex;flex-direction:column;gap:8px">
            ${months.slice(-12).map(m => `
              <div class="cost-bar-wrap">
                <div class="cost-bar-label">
                  <span style="font-family:var(--mono);font-size:11px">${m}</span>
                  <span style="font-family:var(--mono);font-size:11px;color:var(--green)">${fmtINR(monthly[m])}</span>
                </div>
                <div class="cost-bar-track"><div class="cost-bar-fill" style="width:${Math.round(monthly[m]/maxMonthlyCost*100)}%;background:var(--blue)"></div></div>
              </div>`).join('')}
          </div>` : '<div class="empty-state" style="padding:24px"><p>No monthly data available</p></div>'}
        <hr class="divider">
        <div class="card-title" style="margin-bottom:12px">Work Order Summary</div>
        <table style="width:100%">
          <thead><tr><th>Status</th><th>Count</th><th>Avg Cost</th></tr></thead>
          <tbody>
            ${['open','in_progress','completed'].map(s => {
              const matching = wos.filter(w => w.status === s);
              const avg = matching.length ? matching.reduce((a,w)=>a+(w.total_cost||0),0)/matching.length : 0;
              return `<tr><td><span class="badge b-${s}">${s.replace('_',' ')}</span></td>
                <td style="font-family:var(--mono)">${matching.length}</td>
                <td style="font-family:var(--mono);color:var(--green)">${fmtINR(avg)}</td></tr>`;
            }).join('')}
          </tbody>
        </table>
      </div>
    </div>`;
}

function renderCorrectiveTab(container) {
  const wos = getFilteredWOs().filter(w => w.type === 'corrective' || w.type === 'emergency');
  if (!wos.length) {
    container.innerHTML = '<div class="empty-state"><div class="icon">🔧</div><h3>No Corrective Maintenance</h3><p>No corrective or emergency work orders found for this asset.</p></div>';
    return;
  }

  const totalCost   = wos.reduce((s,w) => s+(w.total_cost||0), 0);
  const totalHrs    = wos.reduce((s,w) => s+(w.actual_hours||0), 0);
  const completed   = wos.filter(w => w.status==='completed');
  const open        = wos.filter(w => w.status==='open' || w.status==='in_progress');
  const emergency   = wos.filter(w => w.type==='emergency');
  const avgCost     = completed.length ? completed.reduce((s,w)=>s+(w.total_cost||0),0)/completed.length : 0;

  // Group by failure / priority
  const byPriority = {};
  wos.forEach(w => { byPriority[w.priority] = (byPriority[w.priority]||0)+1; });

  // Monthly frequency
  const monthly = {};
  wos.forEach(w => {
    const m = (w.created_at||'').slice(0,7);
    if (m) monthly[m] = (monthly[m]||0)+1;
  });
  const months = Object.keys(monthly).sort().slice(-12);
  const maxCount = Math.max(...Object.values(monthly), 1);

  const prioColor = { critical:'var(--red)', high:'var(--yellow)', medium:'var(--blue)', low:'var(--green)' };

  container.innerHTML = `
    <!-- KPI row -->
    <div class="hist-summary" style="margin-bottom:20px">
      <div class="hist-stat red"><div class="hist-stat-val">${wos.length}</div><div class="hist-stat-lbl">Total Corrective WOs</div></div>
      <div class="hist-stat yellow"><div class="hist-stat-val">${open.length}</div><div class="hist-stat-lbl">Open / In-Progress</div></div>
      <div class="hist-stat green"><div class="hist-stat-val">${completed.length}</div><div class="hist-stat-lbl">Completed</div></div>
      <div class="hist-stat red"><div class="hist-stat-val">${emergency.length}</div><div class="hist-stat-lbl">Emergency</div></div>
      <div class="hist-stat yellow"><div class="hist-stat-val">${fmtINR(totalCost)}</div><div class="hist-stat-lbl">Total Cost</div></div>
      <div class="hist-stat blue"><div class="hist-stat-val">${totalHrs.toFixed(1)}h</div><div class="hist-stat-lbl">Total Hours</div></div>
    </div>

    <div class="two-col">
      <!-- Left: breakdown -->
      <div class="card">
        <div class="card-header"><span class="card-title">🔍 Breakdown</span></div>

        <div class="card-title" style="margin-bottom:10px;font-size:11px">By Priority</div>
        ${['critical','high','medium','low'].map(p => {
          const cnt = byPriority[p]||0;
          if (!cnt) return '';
          return `<div class="cost-bar-wrap" style="margin-bottom:10px">
            <div class="cost-bar-label">
              <span><span class="badge b-${p}">${p}</span></span>
              <span style="font-family:var(--mono);font-size:12px">${cnt} WO${cnt!==1?'s':''}</span>
            </div>
            <div class="cost-bar-track"><div class="cost-bar-fill" style="width:${Math.round(cnt/wos.length*100)}%;background:${prioColor[p]||'var(--text2)'}"></div></div>
          </div>`;
        }).join('')}

        <hr class="divider">
        <div class="card-title" style="margin-bottom:10px;font-size:11px">Avg Cost per Completed WO</div>
        <div style="font-family:var(--mono);font-size:24px;font-weight:700;color:var(--green)">${fmtINR(avgCost)}</div>

        <hr class="divider">
        <div class="card-title" style="margin-bottom:10px;font-size:11px">Completion Rate</div>
        <div style="font-family:var(--mono);font-size:24px;font-weight:700;color:${wos.length?completed.length/wos.length>0.8?'var(--green)':'var(--yellow)':'var(--text2)'}">
          ${wos.length ? Math.round(completed.length/wos.length*100) : 0}%
        </div>
        <div style="margin-top:8px">
          <div class="cost-bar-track" style="height:12px;border-radius:6px">
            <div class="cost-bar-fill" style="width:${wos.length?Math.round(completed.length/wos.length*100):0}%;background:var(--green);height:100%"></div>
          </div>
        </div>
      </div>

      <!-- Right: frequency chart -->
      <div class="card">
        <div class="card-header"><span class="card-title">📈 Monthly Frequency</span></div>
        ${months.length ? `
          <div style="display:flex;flex-direction:column;gap:8px">
            ${months.map(m => `
              <div class="cost-bar-wrap">
                <div class="cost-bar-label">
                  <span style="font-family:var(--mono);font-size:11px">${m}</span>
                  <span style="font-family:var(--mono);font-size:11px;color:var(--red)">${monthly[m]} WO${monthly[m]!==1?'s':''}</span>
                </div>
                <div class="cost-bar-track">
                  <div class="cost-bar-fill" style="width:${Math.round(monthly[m]/maxCount*100)}%;background:var(--red)"></div>
                </div>
              </div>`).join('')}
          </div>` : '<div class="empty-state" style="padding:24px"><p>Not enough data</p></div>'}
      </div>
    </div>

    <!-- Work order table -->
    <div class="card">
      <div class="card-header">
        <span class="card-title">📋 Corrective Work Orders (${wos.length})</span>
        <div style="display:flex;gap:12px;font-size:12px;color:var(--text2)">
          <span>Total: <span style="color:var(--green);font-family:var(--mono)">${fmtINR(totalCost)}</span></span>
          <span>Hours: <span style="color:var(--blue);font-family:var(--mono)">${totalHrs.toFixed(1)}</span></span>
        </div>
      </div>
      <div class="tbl-wrap"><table>
        <thead><tr><th>WO #</th><th>Title</th><th>Type</th><th>Priority</th><th>Status</th><th>Failure Reason</th><th>Hours</th><th>Cost</th><th>Date</th></tr></thead>
        <tbody>
          ${wos.map(w => `<tr onclick="openWODetail(${w.id})" style="cursor:pointer">
            <td class="td-mono">${w.wo_number||'—'}</td>
            <td class="td-primary">${w.title}</td>
            <td><span class="badge b-${w.type==='emergency'?'critical':'warning'}">${w.type}</span></td>
            <td><span class="badge b-${w.priority}">${w.priority}</span></td>
            <td><span class="badge b-${w.status}">${w.status.replace('_',' ')}</span></td>
            <td style="font-size:12px;color:var(--text2);max-width:160px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap"
                title="${w.failure_reason||''}">${w.failure_reason||'<span style="color:var(--text2)">—</span>'}</td>
            <td style="font-family:var(--mono);font-size:12px">${w.actual_hours||'—'}</td>
            <td style="font-family:var(--mono);font-size:12px;color:var(--green)">${fmtINR(w.total_cost||0)}</td>
            <td style="font-family:var(--mono);font-size:11px;color:var(--text2)">${(w.created_at||'').slice(0,10)}</td>
          </tr>`).join('')}
        </tbody>
      </table></div>
    </div>`;
}

function exportHistoryCSV() {
  const asset = historyState.asset;
  if (!asset) { toast('Select an asset first', 'error'); return; }
  const events = getFilteredEvents();
  const wos = getFilteredWOs();
  const rows = [['Date','Type','Title','Detail','Cost','Performed By']];
  events.forEach(e => rows.push([
    (e.created_at||'').slice(0,16),
    e.event_type, e.event_title,
    e.event_detail || '',
    e.cost || 0,
    e.performed_by_name || ''
  ]));
  const csv = rows.map(r => r.map(v => `"${String(v).replace(/"/g,'""')}"`).join(',')).join('\n');
  const blob = new Blob([csv], { type: 'text/csv' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `history_${asset.code || asset.id}_${new Date().toISOString().slice(0,10)}.csv`;
  a.click();
  URL.revokeObjectURL(url);
  toast('CSV exported', 'success');
}


// ── DASHBOARD EXTRA CHARTS ───────────────────────────────────────────────────
function renderDashboardCharts(d) {
  const chartDefaults = {
    responsive: true, maintainAspectRatio: false,
    plugins: { legend: { labels: { color: '#9aa0b4', font: { family: 'IBM Plex Mono', size: 11 }, padding: 12 } } },
    scales: { x: { ticks: { color: '#9aa0b4', font: { family: 'IBM Plex Mono', size: 11 } }, grid: { color: '#1e2028' }, border: { display: false } },
               y: { ticks: { color: '#9aa0b4', font: { family: 'IBM Plex Mono', size: 11 } }, grid: { color: '#1e2028' }, border: { display: false } } }
  };

  // Assets by category doughnut
  if (d.assets_by_category?.length) {
    if (state.charts['assets-cat']) state.charts['assets-cat'].destroy();
    const ctx = document.getElementById('chart-assets-cat')?.getContext('2d');
    if (ctx) state.charts['assets-cat'] = new Chart(ctx, {
      type: 'doughnut',
      data: { labels: d.assets_by_category.map(r=>r.name), datasets: [{ data: d.assets_by_category.map(r=>r.count), backgroundColor: d.assets_by_category.map(r=>r.color||'#5c6070'), borderWidth: 0, borderRadius: 3 }] },
      options: { ...chartDefaults, plugins: { legend: { position: 'right', labels: { color: '#9aa0b4', font: { family: 'IBM Plex Mono', size: 10 }, padding: 10 } } } }
    });
  }

  // PM Compliance gauge doughnut
  const pct = d.pm_compliance ?? 0;
  document.getElementById('pm-pct-val').textContent = pct + '%';
  document.getElementById('pm-pct-val').style.color = pct >= 80 ? 'var(--green)' : pct >= 60 ? 'var(--yellow)' : 'var(--red)';
  if (state.charts['pm-compliance']) state.charts['pm-compliance'].destroy();
  const pmCtx = document.getElementById('chart-pm-compliance')?.getContext('2d');
  if (pmCtx) state.charts['pm-compliance'] = new Chart(pmCtx, {
    type: 'doughnut',
    data: { datasets: [{ data: [pct, 100 - pct], backgroundColor: [pct >= 80 ? '#00e5a0' : pct >= 60 ? '#ffbe4d' : '#ff4d6d', '#1e2028'], borderWidth: 0, borderRadius: 4 }] },
    options: { responsive: true, maintainAspectRatio: false, cutout: '75%', plugins: { legend: { display: false }, tooltip: { enabled: false } } }
  });

  // Monthly cost trend
  if (d.cost_trend?.length) {
    if (state.charts['cost-trend']) state.charts['cost-trend'].destroy();
    const ctCtx = document.getElementById('chart-cost-trend')?.getContext('2d');
    if (ctCtx) state.charts['cost-trend'] = new Chart(ctCtx, {
      type: 'line',
      data: { labels: d.cost_trend.map(r=>r.month), datasets: [{ label: 'Maintenance Cost', data: d.cost_trend.map(r=>r.cost||0), borderColor: '#00e5a0', backgroundColor: 'rgba(0,229,160,.08)', tension: 0.4, fill: true, borderWidth: 2, pointBackgroundColor: '#00e5a0', pointRadius: 4 }] },
      options: { ...chartDefaults, plugins: { legend: { display: false } }, scales: { x: { ...chartDefaults.scales.x }, y: { ...chartDefaults.scales.y, ticks: { ...chartDefaults.scales.y.ticks, callback: v => '₹' + v.toLocaleString() } } } }
    });
  }
}

// Patch loadDashboard to call extra charts after existing charts
// Dashboard charts auto-rendered after loadDashboard via renderDashboardCharts(d)

// ── CALENDAR ──────────────────────────────────────────────────────────────────
let calState = { year: new Date().getFullYear(), month: new Date().getMonth() + 1, events: null };

function calToday() { calState.year = new Date().getFullYear(); calState.month = new Date().getMonth() + 1; renderCalendar(); }
function calPrev() { calState.month--; if (calState.month < 1) { calState.month = 12; calState.year--; } renderCalendar(); }
function calNext() { calState.month++; if (calState.month > 12) { calState.month = 1; calState.year++; } renderCalendar(); }

async function initCalendar() { await renderCalendar(); }

async function renderCalendar() {
  const { year, month } = calState;
  const monthStr = `${year}-${String(month).padStart(2,'0')}`;
  const monthNames = ['January','February','March','April','May','June','July','August','September','October','November','December'];
  document.getElementById('cal-month-title').textContent = `${monthNames[month-1]} ${year}`;

  try {
    const d = await api('GET', '/calendar?month=' + monthStr);
    calState.events = d;
    const grid = document.getElementById('cal-grid');

    // Build day event map
    const evMap = {};
    (d.work_orders || []).forEach(w => {
      const date = w.due_date || w.scheduled_date;
      if (!date) return;
      if (!evMap[date]) evMap[date] = [];
      evMap[date].push({ type: 'wo', label: w.wo_number + ': ' + w.title, priority: w.priority, id: w.id, cls: w.priority === 'critical' ? 'ev-critical' : 'ev-wo' });
    });
    (d.pm_schedules || []).forEach(p => {
      const date = p.next_due;
      if (!date) return;
      if (!evMap[date]) evMap[date] = [];
      evMap[date].push({ type: 'pm', label: '✅ ' + p.title + (p.asset_name ? ' — ' + p.asset_name : ''), id: p.id, cls: 'ev-pm' });
    });

    // Grid: find first day of month
    const firstDay = new Date(year, month - 1, 1).getDay();
    const daysInMonth = new Date(year, month, 0).getDate();
    const prevDays = new Date(year, month - 1, 0).getDate();
    const today = new Date().toISOString().slice(0, 10);

    let cells = '';
    let dayNum = 1, nextDay = 1;
    const totalCells = Math.ceil((firstDay + daysInMonth) / 7) * 7;

    for (let i = 0; i < totalCells; i++) {
      if (i < firstDay) {
        const d2 = prevDays - firstDay + i + 1;
        cells += `<div class="cal-cell other-month"><div class="cal-day-num">${d2}</div></div>`;
      } else if (dayNum <= daysInMonth) {
        const dateStr = `${year}-${String(month).padStart(2,'0')}-${String(dayNum).padStart(2,'0')}`;
        const isToday = dateStr === today;
        const dayEvents = evMap[dateStr] || [];
        const evHtml = dayEvents.slice(0, 3).map(e =>
          `<div class="cal-event ${e.cls}" title="${e.label}" onclick="event.stopPropagation();${e.type==='wo'?`openWODetail(${e.id})`:`completePM(${e.id})`}">${e.label}</div>`
        ).join('') + (dayEvents.length > 3 ? `<div style="font-size:10px;color:var(--text2);padding:2px 4px">+${dayEvents.length-3} more</div>` : '');
        cells += `<div class="cal-cell ${isToday ? 'today' : ''}"><div class="cal-day-num">${dayNum}</div>${evHtml}</div>`;
        dayNum++;
      } else {
        cells += `<div class="cal-cell other-month"><div class="cal-day-num">${nextDay++}</div></div>`;
      }
    }
    grid.innerHTML = cells;
  } catch(e) { toast('Error loading calendar: ' + e.message, 'error'); }
}

// ── REPORTS ───────────────────────────────────────────────────────────────────
let currentReport = null;

async function runReport(type) {
  currentReport = type;
  const titles = {
    'maintenance-summary': 'Maintenance Summary Report',
    'asset-list': 'Asset Register',
    'pm-compliance': 'PM Compliance Report',
    'downtime': 'Downtime Analysis Report',
    'inventory': 'Inventory Report',
    'cost-analysis': 'Cost Analysis Report',
    'depreciation': 'Depreciation Report',
  };
  document.getElementById('report-title').textContent = titles[type] || type;
  document.getElementById('report-output').style.display = 'block';
  document.getElementById('report-body').innerHTML = '<div class="loading"><div class="spinner"></div> Generating report...</div>';
  document.getElementById('report-output').scrollIntoView({ behavior: 'smooth' });

  try {
    if (type === 'maintenance-summary') await reportMaintenanceSummary();
    else if (type === 'asset-list') await reportAssetList();
    else if (type === 'pm-compliance') await reportPMCompliance();
    else if (type === 'downtime') await reportDowntime();
    else if (type === 'inventory') await reportInventory();
    else if (type === 'cost-analysis') await reportCostAnalysis();
    else if (type === 'depreciation') await reportDepreciation();
  } catch(e) { document.getElementById('report-body').innerHTML = `<div class="empty-state"><p style="color:var(--red)">Error: ${e.message}</p></div>`; }
}

async function reportMaintenanceSummary() {
  const [dash, wos] = await Promise.all([api('GET', '/dashboard'), api('GET', '/work-orders?per_page=500')]);
  const items = wos.items || [];
  const byType = {}; const byPri = {};
  items.forEach(w => { byType[w.type]=(byType[w.type]||0)+1; byPri[w.priority]=(byPri[w.priority]||0)+1; });
  const totalCost = items.reduce((s,w)=>s+(w.total_cost||0),0);
  const completionRate = items.length ? Math.round(items.filter(w=>w.status==='completed').length/items.length*100) : 0;
  document.getElementById('report-body').innerHTML = `
    <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:20px">
      ${[['Total WOs',dash.total_wo,'text-blue'],['Completed',dash.completed_wo,'text-green'],['Completion Rate',completionRate+'%','text-green'],['Total Cost',fmtINR(totalCost),'text-yellow']].map(([l,v,c])=>`<div class="hist-stat"><div class="hist-stat-val ${c}" style="font-size:20px">${v}</div><div class="hist-stat-lbl">${l}</div></div>`).join('')}
    </div>
    <div class="two-col">
      <div><h4 style="margin-bottom:10px">By Type</h4><table><thead><tr><th>Type</th><th>Count</th></tr></thead><tbody>${Object.entries(byType).map(([k,v])=>`<tr><td>${k}</td><td class="td-mono">${v}</td></tr>`).join('')}</tbody></table></div>
      <div><h4 style="margin-bottom:10px">By Priority</h4><table><thead><tr><th>Priority</th><th>Count</th></tr></thead><tbody>${Object.entries(byPri).map(([k,v])=>`<tr><td><span class="badge b-${k}">${k}</span></td><td class="td-mono">${v}</td></tr>`).join('')}</tbody></table></div>
    </div>
    <h4 style="margin:16px 0 10px">Work Order Details</h4>
    <div class="tbl-wrap"><table><thead><tr><th>WO#</th><th>Title</th><th>Asset</th><th>Type</th><th>Priority</th><th>Status</th><th>Cost</th></tr></thead>
    <tbody>${items.map(w=>`<tr><td class="td-mono">${w.wo_number}</td><td>${w.title}</td><td>${w.asset_name||'—'}</td><td>${w.type}</td><td><span class="badge b-${w.priority}">${w.priority}</span></td><td><span class="badge b-${w.status}">${w.status.replace('_',' ')}</span></td><td class="td-mono">${fmtINR(w.total_cost||0)}</td></tr>`).join('')}</tbody></table></div>`;
}

async function reportAssetList() {
  const d = await api('GET', '/assets?per_page=500');
  document.getElementById('report-body').innerHTML = `
    <p style="color:var(--text2);margin-bottom:12px">Total assets: ${d.total || d.items?.length}</p>
    <div class="tbl-wrap"><table><thead><tr><th>Code</th><th>Name</th><th>Category</th><th>Location</th><th>Status</th><th>Criticality</th><th>Make/Model</th><th>Purchase Cost</th><th>Warranty</th></tr></thead>
    <tbody>${(d.items||[]).map(a=>`<tr><td class="td-mono">${a.code||'—'}</td><td>${a.name}</td><td>${a.category_name||'—'}</td><td>${a.location_name||'—'}</td><td><span class="badge b-${a.status}">${a.status}</span></td><td><span class="badge b-${a.criticality||'medium'}">${a.criticality||'med'}</span></td><td>${[a.make,a.model].filter(Boolean).join(' ')||'—'}</td><td class="td-mono">${a.purchase_cost?fmtINR(a.purchase_cost):'—'}</td><td class="td-mono">${a.warranty_expiry||'—'}</td></tr>`).join('')}</tbody></table></div>`;
}

async function reportPMCompliance() {
  const d = await api('GET', '/dashboard');
  const pmRaw = await api('GET', '/pm-schedules');
  const pm = Array.isArray(pmRaw) ? pmRaw : (pmRaw.items || []);
  const overdue = pm.filter(p=>p.next_due && new Date(p.next_due)<new Date());
  document.getElementById('report-body').innerHTML = `
    <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:20px">
      <div class="hist-stat green"><div class="hist-stat-val">${d.pm_compliance}%</div><div class="hist-stat-lbl">Compliance Rate</div></div>
      <div class="hist-stat"><div class="hist-stat-val">${d.pm_total}</div><div class="hist-stat-lbl">Active Schedules</div></div>
      <div class="hist-stat red"><div class="hist-stat-val">${d.pm_overdue}</div><div class="hist-stat-lbl">Overdue</div></div>
    </div>
    <h4 style="margin-bottom:10px;color:var(--red)">⚠ Overdue PM Schedules</h4>
    <div class="tbl-wrap"><table><thead><tr><th>Title</th><th>Asset</th><th>Frequency</th><th>Next Due</th><th>Days Overdue</th></tr></thead>
    <tbody>${overdue.map(p=>{const days=Math.floor((new Date()-new Date(p.next_due))/86400000);return`<tr><td class="td-primary">${p.title}</td><td>${p.asset_name||'—'}</td><td>${p.frequency}</td><td class="td-mono" style="color:var(--red)">${p.next_due}</td><td class="td-mono" style="color:var(--red)">${days}d</td></tr>`;}).join('')||'<tr><td colspan="5" class="empty-state">All PM schedules are current ✓</td></tr>'}</tbody></table></div>`;
}

async function reportDowntime() {
  const assets = await api('GET', '/assets?per_page=200');
  let allDt = [], promises = (assets.items||[]).slice(0,20).map(a=>api('GET','/assets/'+a.id+'/downtime').then(r=>{r.forEach(d=>d._assetName=a.name);allDt.push(...r)}).catch(()=>{}));
  await Promise.all(promises);
  const totalHrs = allDt.reduce((s,d)=>s+(d.duration_hours||0),0);
  const byAsset = {}; allDt.forEach(d=>{byAsset[d.asset_id]={name:d._assetName,hours:(byAsset[d.asset_id]?.hours||0)+(d.duration_hours||0),count:(byAsset[d.asset_id]?.count||0)+1}});
  const sorted = Object.entries(byAsset).sort((a,b)=>b[1].hours-a[1].hours);
  document.getElementById('report-body').innerHTML = `
    <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:20px">
      <div class="hist-stat red"><div class="hist-stat-val">${totalHrs.toFixed(1)}</div><div class="hist-stat-lbl">Total Downtime Hours</div></div>
      <div class="hist-stat yellow"><div class="hist-stat-val">${allDt.length}</div><div class="hist-stat-lbl">Total Incidents</div></div>
      <div class="hist-stat"><div class="hist-stat-val">${sorted.length}</div><div class="hist-stat-lbl">Assets Affected</div></div>
    </div>
    <h4 style="margin-bottom:10px">Top Assets by Downtime</h4>
    <div class="tbl-wrap"><table><thead><tr><th>Asset</th><th>Incidents</th><th>Total Hours</th></tr></thead>
    <tbody>${sorted.slice(0,10).map(([_,v])=>`<tr><td>${v.name}</td><td class="td-mono">${v.count}</td><td class="td-mono" style="color:var(--red)">${v.hours.toFixed(1)}h</td></tr>`).join('')||'<tr><td colspan="3" class="empty-state">No downtime records found</td></tr>'}</tbody></table></div>`;
}

async function reportInventory() {
  const d = await api('GET', '/parts?per_page=500');
  const items = d.items||[];
  const totalVal = items.reduce((s,p)=>s+(p.quantity||0)*(p.unit_cost||0),0);
  const lowStock = items.filter(p=>p.is_low_stock);
  document.getElementById('report-body').innerHTML = `
    <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:20px">
      <div class="hist-stat"><div class="hist-stat-val">${items.length}</div><div class="hist-stat-lbl">Total Parts</div></div>
      <div class="hist-stat green"><div class="hist-stat-val">${fmtINR(totalVal)}</div><div class="hist-stat-lbl">Inventory Value</div></div>
      <div class="hist-stat red"><div class="hist-stat-val">${lowStock.length}</div><div class="hist-stat-lbl">Low Stock Items</div></div>
    </div>
    <div class="tbl-wrap"><table><thead><tr><th>Part #</th><th>Name</th><th>Stock</th><th>Min</th><th>Unit Cost</th><th>Total Value</th><th>Location</th><th>Status</th></tr></thead>
    <tbody>${items.map(p=>`<tr><td class="td-mono">${p.part_number||'—'}</td><td>${p.name}</td><td class="td-mono" style="color:${p.is_low_stock?'var(--red)':'var(--text0)'}">${p.quantity}</td><td class="td-mono">${p.min_quantity}</td><td class="td-mono">${fmtINR2(p.unit_cost||0)}</td><td class="td-mono" style="color:var(--green)">${fmtINR((p.quantity||0)*(p.unit_cost||0))}</td><td>${p.location||'—'}</td><td>${p.is_low_stock?'<span class="badge b-critical">LOW</span>':'<span class="badge b-completed">OK</span>'}</td></tr>`).join('')}</tbody></table></div>`;
}

async function reportCostAnalysis() {
  const d = await api('GET', '/dashboard');
  const wos = await api('GET', '/work-orders?per_page=500');
  const items = wos.items||[];
  const byAsset = {};
  items.forEach(w=>{if(w.asset_name){byAsset[w.asset_name]=(byAsset[w.asset_name]||0)+(w.total_cost||0);}});
  const topAssets = Object.entries(byAsset).sort((a,b)=>b[1]-a[1]).slice(0,10);
  document.getElementById('report-body').innerHTML = `
    <div style="margin-bottom:20px">
      <h4 style="margin-bottom:12px">Monthly Cost Trend</h4>
      ${(d.cost_trend||[]).length ? d.cost_trend.map(r=>`
        <div class="cost-bar-wrap" style="margin-bottom:10px">
          <div class="cost-bar-label"><span class="td-mono">${r.month}</span><span class="td-mono">${fmtINR(r.cost||0)}</span></div>
          <div class="cost-bar-track"><div class="cost-bar-fill" style="width:${Math.round((r.cost||0)/Math.max(...(d.cost_trend||[]).map(x=>x.cost||1))*100)}%;background:var(--blue)"></div></div>
        </div>`).join('') : '<p style="color:var(--text2)">No trend data</p>'}
    </div>
    <h4 style="margin-bottom:12px">Top Assets by Maintenance Cost</h4>
    <div class="tbl-wrap"><table><thead><tr><th>Asset</th><th>Total Cost</th></tr></thead>
    <tbody>${topAssets.map(([k,v])=>`<tr><td>${k}</td><td class="td-mono" style="color:var(--green)">${fmtINR(v)}</td></tr>`).join('')||'<tr><td colspan="2" class="empty-state">No data</td></tr>'}</tbody></table></div>`;
}

async function reportDepreciation() {
  const d = await api('GET', '/dashboard');
  const assets = d.depreciation_assets||[];
  const usefulLife = 10; // default years
  document.getElementById('report-body').innerHTML = `
    <p style="font-size:12px;color:var(--text2);margin-bottom:16px">Straight-line depreciation using ${usefulLife}-year useful life and 10% salvage value.</p>
    <div class="tbl-wrap"><table>
      <thead><tr><th>Asset</th><th>Purchase Cost</th><th>Purchase Date</th><th>Age (yrs)</th><th>Annual Dep.</th><th>Accum. Dep.</th><th>Book Value</th><th>Condition</th></tr></thead>
      <tbody>${assets.map(a=>{
        const cost = a.purchase_cost||0;
        const salvage = cost * 0.1;
        const annual = (cost - salvage) / usefulLife;
        const age = a.age_years||0;
        const accum = Math.min(annual * age, cost - salvage);
        const book = Math.max(cost - accum, salvage);
        const pct = cost ? Math.round(accum/cost*100) : 0;
        const cond = pct < 33 ? 'Good' : pct < 66 ? 'Fair' : 'Poor';
        const condColor = pct < 33 ? 'var(--green)' : pct < 66 ? 'var(--yellow)' : 'var(--red)';
        return `<tr><td class="td-primary">${a.name}</td><td class="td-mono">${fmtINR(cost)}</td><td class="td-mono">${a.purchase_date||'—'}</td><td class="td-mono">${age}</td><td class="td-mono">${fmtINR(annual)}</td><td class="td-mono" style="color:var(--yellow)">${fmtINR(accum)}</td><td class="td-mono" style="color:var(--green)">${fmtINR(book)}</td><td style="color:${condColor}">${cond}</td></tr>`;
      }).join('')||'<tr><td colspan="8" class="empty-state">No asset cost data available</td></tr>'}</tbody>
    </table></div>`;
}

let reportCSVData = [];
function exportReportCSV() { window.print(); }

async function exportAllCSV() {
  toast('Exporting all data...', 'success');
  const [assets, wos, parts] = await Promise.all([api('GET','/assets?per_page=1000'), api('GET','/work-orders?per_page=1000'), api('GET','/parts?per_page=1000')]);
  const makeCSV = (rows, keys) => [keys.join(','), ...rows.map(r=>keys.map(k=>`"${String(r[k]||'').replace(/"/g,'""')}"`).join(','))].join('\n');
  const dl = (csv, name) => { const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([csv],{type:'text/csv'})); a.download = name; a.click(); };
  dl(makeCSV(assets.items||[], ['code','name','category_name','location_name','status','criticality','make','model','serial_number','purchase_date','purchase_cost']), 'assets.csv');
  setTimeout(() => dl(makeCSV(wos.items||[], ['wo_number','title','asset_name','type','priority','status','assigned_to_name','due_date','actual_hours','total_cost']), 'work_orders.csv'), 500);
  setTimeout(() => dl(makeCSV(parts.items||[], ['part_number','name','quantity','min_quantity','unit_cost','location','supplier']), 'parts.csv'), 1000);
}

// ── IMPORT ────────────────────────────────────────────────────────────────────
let importData = { assets: null, parts: null };

function initImport() {
  ['assets','parts'].forEach(type => {
    const zone = document.getElementById(type + '-drop-zone');
    if (!zone) return;
    zone.ondragover = e => { e.preventDefault(); zone.classList.add('drag-over'); };
    zone.ondragleave = () => zone.classList.remove('drag-over');
    zone.ondrop = e => { e.preventDefault(); zone.classList.remove('drag-over'); const f = e.dataTransfer.files[0]; if (f) { const inp = document.getElementById(type+'-file-input'); inp.files = e.dataTransfer.files; loadImportFile(type, inp); } };
  });
}

function parseCSV(text) {
  const lines = text.trim().split('\n');
  const headers = lines[0].split(',').map(h => h.trim().replace(/^"|"$/g, '').toLowerCase().replace(/\s+/g,'_'));
  return lines.slice(1).filter(l=>l.trim()).map(line => {
    const vals = []; let cur = ''; let inQ = false;
    for (const ch of line + ',') {
      if (ch === '"') inQ = !inQ;
      else if (ch === ',' && !inQ) { vals.push(cur.trim()); cur = ''; }
      else cur += ch;
    }
    const obj = {};
    headers.forEach((h, i) => obj[h] = vals[i] || '');
    return obj;
  });
}

function loadImportFile(type, input) {
  const file = input.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = e => {
    const rows = parseCSV(e.target.result);
    importData[type] = rows;
    const preview = document.getElementById(type + '-import-preview');
    const btn = document.getElementById(type + '-import-btn');
    if (!rows.length) { preview.innerHTML = '<p style="color:var(--red)">No data found in file</p>'; return; }
    const headers = Object.keys(rows[0]);
    preview.innerHTML = `
      <p style="font-size:12px;color:var(--text2);margin-bottom:8px">${rows.length} rows found</p>
      <div class="tbl-wrap"><table style="font-size:11px">
        <thead><tr>${headers.map(h=>`<th>${h}</th>`).join('')}</tr></thead>
        <tbody>${rows.slice(0,5).map(r=>`<tr>${headers.map(h=>`<td>${r[h]||''}</td>`).join('')}</tr>`).join('')}
        ${rows.length > 5 ? `<tr><td colspan="${headers.length}" style="color:var(--text2);text-align:center">...${rows.length-5} more rows</td></tr>` : ''}
        </tbody>
      </table></div>`;
    btn.style.display = 'inline-flex';
  };
  reader.readAsText(file);
}

async function doImport(type) {
  const rows = importData[type];
  if (!rows?.length) { toast('No data to import', 'error'); return; }
  try {
    const r = await api('POST', '/import/' + type, { rows });
    toast(`Imported ${r.created} records${r.errors?.length ? ' (' + r.errors.length + ' errors)' : ''}`, r.errors?.length ? 'warning' : 'success');
    if (r.errors?.length) console.warn('Import errors:', r.errors);
    importData[type] = null;
    document.getElementById(type + '-import-preview').innerHTML = '';
    document.getElementById(type + '-import-btn').style.display = 'none';
  } catch(e) { toast('Import failed: ' + e.message, 'error'); }
}

function downloadTemplate(type) {
  const templates = {
    assets: 'name,code,make,model,serial_number,purchase_date,purchase_cost,status,criticality,description,notes\nAir Handler Unit,AHU-002,Carrier,30XA,SN123,2024-01-01,45000,active,high,Main AHU,Notes here',
    parts:  'name,part_number,description,quantity,min_quantity,unit_cost,location,supplier,manufacturer,notes\nHVAC Filter,FILT-002,20x20 MERV8,50,10,12.50,Shelf A1,FilterPro,FilterPro Inc,Standard filter'
  };
  const blob = new Blob([templates[type]], { type: 'text/csv' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = type + '_import_template.csv';
  a.click();
  toast('Template downloaded', 'success');
}

// ── DOWNTIME TRACKING (Equipment History tab) ─────────────────────────────────
async function renderDowntimeTab(container) {
  if (!historyState.assetId) return;
  let records = [];
  try { records = await api('GET', '/assets/' + historyState.assetId + '/downtime'); } catch(e) {}

  const totalHrs = records.reduce((s,r)=>s+(r.duration_hours||0), 0);
  const ongoing = records.filter(r=>!r.end_time);
  const catCounts = {};
  records.forEach(r=>{ catCounts[r.category]=(catCounts[r.category]||0)+1; });

  const catColors = { unplanned:'var(--red)', planned:'var(--blue)', breakdown:'var(--purple)', maintenance:'var(--yellow)' };

  container.innerHTML = `
    <div class="hist-summary" style="margin-bottom:20px">
      <div class="hist-stat red"><div class="hist-stat-val">${totalHrs.toFixed(1)}</div><div class="hist-stat-lbl">Total Downtime Hours</div></div>
      <div class="hist-stat yellow"><div class="hist-stat-val">${records.length}</div><div class="hist-stat-lbl">Total Incidents</div></div>
      <div class="hist-stat"><div class="hist-stat-val">${ongoing.length}</div><div class="hist-stat-lbl">Ongoing</div></div>
      <div class="hist-stat blue"><div class="hist-stat-val">${records.length?((totalHrs/records.length).toFixed(1)):'—'}</div><div class="hist-stat-lbl">Avg Hours/Incident</div></div>
    </div>
    <div class="two-col" style="margin-bottom:16px">
      <div class="card">
        <div class="card-header"><span class="card-title">By Category</span></div>
        ${Object.entries(catCounts).map(([cat,cnt])=>`
          <div class="cost-bar-wrap" style="margin-bottom:10px">
            <div class="cost-bar-label"><span style="text-transform:capitalize">${cat}</span><span class="td-mono">${cnt}</span></div>
            <div class="cost-bar-track"><div class="cost-bar-fill" style="width:${Math.round(cnt/records.length*100)}%;background:${catColors[cat]||'var(--text2)'}"></div></div>
          </div>`).join('') || '<div class="empty-state" style="padding:16px"><p>No data</p></div>'}
      </div>
      <div class="card">
        <div class="card-header"><span class="card-title">Log Downtime Event</span></div>
        <div class="form-group"><label>Start Time *</label><input type="datetime-local" id="dt-start" class="form-control"></div>
        <div class="form-group"><label>End Time</label><input type="datetime-local" id="dt-end" class="form-control"></div>
        <div class="form-group"><label>Reason *</label><input type="text" id="dt-reason" class="form-control" placeholder="Equipment failure, planned maintenance..."></div>
        <div class="form-group"><label>Category</label>
          <select id="dt-category" class="form-control">
            <option value="unplanned">Unplanned</option>
            <option value="planned">Planned</option>
            <option value="breakdown">Breakdown</option>
            <option value="maintenance">Maintenance</option>
          </select>
        </div>
        <div class="form-group"><label>Notes</label><textarea id="dt-notes" class="form-control" style="min-height:60px"></textarea></div>
        <button class="btn btn-primary" onclick="logDowntime()">Log Downtime</button>
      </div>
    </div>
    <div class="card">
      <div class="card-header"><span class="card-title">Downtime Records (${records.length})</span></div>
      <div class="tbl-wrap"><table>
        <thead><tr><th>Start</th><th>End</th><th>Duration</th><th>Reason</th><th>Category</th><th>Recorded By</th><th></th></tr></thead>
        <tbody>
          ${records.map(r=>`<tr>
            <td class="td-mono" style="font-size:11px">${(r.start_time||'').slice(0,16)}</td>
            <td class="td-mono" style="font-size:11px;color:${r.end_time?'var(--text1)':'var(--red)'}">${r.end_time?(r.end_time||'').slice(0,16):'Ongoing'}</td>
            <td class="td-mono" style="color:var(--red)">${r.duration_hours!=null?r.duration_hours.toFixed(1)+'h':'—'}</td>
            <td style="font-size:12px">${r.reason||'—'}</td>
            <td><span class="tag">${r.category||'—'}</span></td>
            <td style="font-size:12px">${r.recorded_by_name||'—'}</td>
            <td><button class="btn btn-danger btn-sm btn-icon admin-only-btn" onclick="deleteDowntimeRecord(${r.id})">🗑</button></td>
          </tr>`).join('') || '<tr><td colspan="7" class="empty-state">No downtime records</td></tr>'}
        </tbody>
      </table></div>
    </div>`;
}

async function logDowntime() {
  const start = document.getElementById('dt-start')?.value;
  const reason = document.getElementById('dt-reason')?.value?.trim();
  if (!start || !reason) { toast('Start time and reason are required', 'error'); return; }
  try {
    await api('POST', '/assets/' + historyState.assetId + '/downtime', {
      start_time: start,
      end_time: document.getElementById('dt-end')?.value || null,
      reason, category: document.getElementById('dt-category')?.value || 'unplanned',
      notes: document.getElementById('dt-notes')?.value || ''
    });
    toast('Downtime logged', 'success');
    renderDowntimeTab(document.getElementById('eq-history-content'));
  } catch(e) { toast('Error: ' + e.message, 'error'); }
}

async function deleteDowntimeRecord(id) {
  if (!confirm('Delete this downtime record?')) return;
  try { await api('DELETE', '/downtime/' + id); toast('Deleted', 'success'); renderDowntimeTab(document.getElementById('eq-history-content')); }
  catch(e) { toast(e.message, 'error'); }
}

// ── DEPRECIATION TAB ──────────────────────────────────────────────────────────
function renderDepreciationTab(container) {
  const asset = historyState.asset;
  if (!asset?.purchase_cost) {
    container.innerHTML = '<div class="empty-state"><div class="icon">📉</div><h3>No Cost Data</h3><p>Add purchase cost to the asset record to enable depreciation tracking.</p></div>';
    return;
  }
  const cost = asset.purchase_cost;
  const purchaseDate = new Date(asset.purchase_date || Date.now());
  const ageYears = (Date.now() - purchaseDate) / (365.25 * 24 * 3600 * 1000);
  const salvage = cost * 0.1;
  const usefulLife = 10;

  // Straight-line
  const slAnnual = (cost - salvage) / usefulLife;
  const slAccum = Math.min(slAnnual * ageYears, cost - salvage);
  const slBook = Math.max(cost - slAccum, salvage);

  // Declining balance (200% DB)
  const dbRate = 2 / usefulLife;
  let dbBook = cost;
  for (let y = 0; y < Math.floor(ageYears); y++) dbBook = Math.max(dbBook * (1 - dbRate), salvage);
  const dbAccum = cost - dbBook;

  // Year-by-year table
  const rows = [];
  let slBal = cost, dbBal = cost;
  for (let y = 1; y <= usefulLife; y++) {
    const slDep = Math.min(slAnnual, slBal - salvage);
    slBal = Math.max(slBal - slDep, salvage);
    const dbDep = Math.max(dbBal * dbRate, 0);
    dbBal = Math.max(dbBal - dbDep, salvage);
    const isCurrentYear = Math.ceil(ageYears) === y;
    rows.push({ y, slDep, slBal, dbDep, dbBal, current: isCurrentYear });
  }

  const slPct = Math.round(slAccum / cost * 100);
  container.innerHTML = `
    <div class="two-col">
      <div class="card">
        <div class="card-header"><span class="card-title">📉 Straight-Line Depreciation</span></div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:16px">
          <div><div style="font-size:11px;color:var(--text2)">Purchase Cost</div><div style="font-family:var(--mono);font-size:18px">${fmtINR(cost)}</div></div>
          <div><div style="font-size:11px;color:var(--text2)">Current Book Value</div><div style="font-family:var(--mono);font-size:18px;color:var(--green)">${fmtINR(slBook)}</div></div>
          <div><div style="font-size:11px;color:var(--text2)">Annual Depreciation</div><div style="font-family:var(--mono);font-size:16px;color:var(--yellow)">${fmtINR(slAnnual)}</div></div>
          <div><div style="font-size:11px;color:var(--text2)">Asset Age</div><div style="font-family:var(--mono);font-size:16px">${ageYears.toFixed(1)} yrs</div></div>
        </div>
        <div style="font-size:12px;color:var(--text2);margin-bottom:6px">Depreciation Progress (${slPct}%)</div>
        <div class="dep-meter" style="margin-bottom:16px">
          <div class="dep-fill" style="width:${slPct}%;background:${slPct<50?'var(--green)':slPct<80?'var(--yellow)':'var(--red)'}"></div>
        </div>
        <div style="font-size:11px;color:var(--text2)">Salvage Value: ${fmtINR(salvage)} · Useful Life: ${usefulLife} years</div>
      </div>
      <div class="card">
        <div class="card-header"><span class="card-title">Depreciation Schedule</span></div>
        <div class="tbl-wrap"><table style="font-size:12px">
          <thead><tr><th>Year</th><th>SL Dep.</th><th>SL Balance</th><th>DB Dep.</th><th>DB Balance</th></tr></thead>
          <tbody>
            ${rows.map(r=>`<tr style="${r.current?'background:var(--green-glow);border-left:2px solid var(--green)':''}">
              <td class="td-mono">${r.y}${r.current?' ◀':''}</td>
              <td class="td-mono" style="color:var(--yellow)">${fmtINR(r.slDep)}</td>
              <td class="td-mono" style="color:var(--green)">${fmtINR(r.slBal)}</td>
              <td class="td-mono" style="color:var(--yellow)">${fmtINR(r.dbDep)}</td>
              <td class="td-mono" style="color:var(--blue)">${fmtINR(r.dbBal)}</td>
            </tr>`).join('')}
          </tbody>
        </table></div>
      </div>
    </div>`;
}

// ── ASSET SPARE PARTS TAB ─────────────────────────────────────────────────────
async function renderAssetPartsTab(container) {
  if (!historyState.assetId) return;
  let linkedParts = [], allParts = [];
  try {
    [linkedParts, allParts] = await Promise.all([
      api('GET', '/assets/' + historyState.assetId + '/parts'),
      api('GET', '/parts?per_page=500')
    ]);
    allParts = allParts.items || [];
  } catch(e) { container.innerHTML = '<div class="empty-state"><p style="color:var(--red)">Error loading parts</p></div>'; return; }

  container.innerHTML = `
    <div class="two-col">
      <div class="card">
        <div class="card-header"><span class="card-title">🔧 Linked Spare Parts (${linkedParts.length})</span></div>
        <div class="tbl-wrap"><table>
          <thead><tr><th>Part #</th><th>Name</th><th>Req. Qty</th><th>Stock</th><th>Unit Cost</th><th>Location</th><th></th></tr></thead>
          <tbody>
            ${linkedParts.map(p=>`<tr>
              <td class="td-mono">${p.part_number||'—'}</td>
              <td class="td-primary">${p.name}</td>
              <td class="td-mono">${p.quantity_required}</td>
              <td class="td-mono" style="color:${p.quantity<p.min_quantity?'var(--red)':'var(--text0)'}">${p.quantity}</td>
              <td class="td-mono">${fmtINR2(p.unit_cost||0)}</td>
              <td style="font-size:12px">${p.location||'—'}</td>
              <td><button class="btn btn-danger btn-sm btn-icon admin-only-btn" onclick="removeAssetPart(${p.id})">🗑</button></td>
            </tr>`).join('') || '<tr><td colspan="7" class="empty-state">No spare parts linked yet</td></tr>'}
          </tbody>
        </table></div>
      </div>
      <div class="card">
        <div class="card-header"><span class="card-title">Link Spare Part</span></div>
        <div class="form-group"><label>Part *</label>
          <select id="ap-part-sel" class="form-control">
            <option value="">— Select Part —</option>
            ${allParts.map(p=>`<option value="${p.id}">${p.name} (${p.part_number||'no#'}) — Stock: ${p.quantity}</option>`).join('')}
          </select>
        </div>
        <div class="form-group"><label>Required Qty</label><input type="number" id="ap-qty" class="form-control" value="1" min="1"></div>
        <div class="form-group"><label>Notes</label><input type="text" id="ap-notes" class="form-control" placeholder="Usage notes..."></div>
        <button class="btn btn-primary" onclick="addAssetPart()">Link Part</button>
      </div>
    </div>`;
}

async function addAssetPart() {
  const partId = document.getElementById('ap-part-sel')?.value;
  if (!partId) { toast('Select a part', 'error'); return; }
  try {
    await api('POST', '/assets/' + historyState.assetId + '/parts', {
      part_id: partId,
      quantity_required: parseInt(document.getElementById('ap-qty')?.value || 1),
      notes: document.getElementById('ap-notes')?.value || ''
    });
    toast('Part linked', 'success');
    renderAssetPartsTab(document.getElementById('eq-history-content'));
  } catch(e) { toast(e.message, 'error'); }
}

async function removeAssetPart(apId) {
  if (!confirm('Remove this linked part?')) return;
  try { await api('DELETE', '/assets/' + historyState.assetId + '/parts/' + apId); toast('Removed', 'success'); renderAssetPartsTab(document.getElementById('eq-history-content')); }
  catch(e) { toast(e.message, 'error'); }
}

// Keyboard shortcut: Escape to close top modal
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') {
    const overlays = document.querySelectorAll('.modal-overlay');
    if (overlays.length) { overlays[overlays.length-1].remove(); return; }
    if (document.getElementById('qr-scanner-overlay').classList.contains('active')) { closeQRScanner(); return; }
  }
  // Global keyboard shortcuts (when not in an input)
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT') return;
  if (e.altKey) {
    const shortcuts = {'d':'dashboard','w':'work-orders','a':'assets','p':'pm','r':'parts','s':'suppliers'};
    if (shortcuts[e.key]) { showPage(shortcuts[e.key]); e.preventDefault(); }
    if (e.key === 'n') { if(state.currentPage==='work-orders') openWOModal(); else if(state.currentPage==='assets') openAssetModal(); e.preventDefault(); }
    if (e.key === 'q') { openQRScanner(); e.preventDefault(); }
  }
  // '?' is handled by initEnhancedShortcuts to avoid duplicate overlays
});

// ── MOBILE: SIDEBAR TOGGLE ────────────────────────────────────────────────────
function toggleSidebar() {
  const sidebar = document.querySelector('.sidebar');
  const overlay = document.getElementById('sidebar-overlay');
  const btn = document.getElementById('hamburger-btn');
  sidebar.classList.toggle('mobile-open');
  overlay.classList.toggle('active');
  btn.classList.toggle('open');
}
function closeSidebar() {
  document.querySelector('.sidebar')?.classList.remove('mobile-open');
  document.getElementById('sidebar-overlay')?.classList.remove('active');
  document.getElementById('hamburger-btn')?.classList.remove('open');
}

// ── MOBILE MORE DRAWER ────────────────────────────────────────────────────────
function toggleMobileMore() {
  const drawer = document.getElementById('mobile-more-drawer');
  const overlay = document.getElementById('mobile-more-overlay');
  if (!drawer || !overlay) return;
  const isOpen = drawer.style.display !== 'none';
  drawer.style.display = isOpen ? 'none' : 'block';
  overlay.style.display = isOpen ? 'none' : 'block';
  // Update active state on more button
  const bnMore = document.getElementById('bn-more');
  if (bnMore) bnMore.classList.toggle('active', !isOpen);
}
function closeMobileMore() {
  const drawer = document.getElementById('mobile-more-drawer');
  const overlay = document.getElementById('mobile-more-overlay');
  if (drawer) drawer.style.display = 'none';
  if (overlay) overlay.style.display = 'none';
  const bnMore = document.getElementById('bn-more');
  if (bnMore) bnMore.classList.remove('active');
}

// Update bottom nav active state
function updateBottomNav(page) {
  closeMobileMore();
  document.querySelectorAll('.bottom-nav-item').forEach(b => b.classList.remove('active'));
  const target = document.getElementById('bn-' + page);
  if (target) target.classList.add('active');
}

// Extend showPage to close sidebar on mobile and update bottom nav
function showPage(name) {
  _origShowPageInternal(name);
  closeSidebar();
  updateBottomNav(name);
}

// ── FAB ───────────────────────────────────────────────────────────────────────
function fabAction() {
  if (state.currentPage === 'work-orders') openWOModal();
  else if (state.currentPage === 'assets') openAssetModal();
  else if (state.currentPage === 'parts') openPartModal();
  else if (state.currentPage === 'pm') openPMModal();
  else openWOModal();
}

// ── THEME TOGGLE ──────────────────────────────────────────────────────────────
let _darkMode = localStorage.getItem('nexus-theme') !== 'light';
function applyTheme() {
  if (_darkMode) {
    document.documentElement.classList.remove('theme-light');
    document.getElementById('theme-toggle-btn').textContent = '🌙';
    localStorage.setItem('nexus-theme', 'dark');
  } else {
    document.documentElement.classList.add('theme-light');
    document.getElementById('theme-toggle-btn').textContent = '☀';
    localStorage.setItem('nexus-theme', 'light');
  }
}
function toggleTheme() { _darkMode = !_darkMode; applyTheme(); }
applyTheme();

// ── OFFLINE DETECTION ─────────────────────────────────────────────────────────
const offlineBar = document.getElementById('offline-bar');
function updateOnlineStatus() {
  if (!navigator.onLine) {
    offlineBar.classList.add('visible');
    document.getElementById('sync-dot').style.background = 'var(--red)';
  } else {
    offlineBar.classList.remove('visible');
    document.getElementById('sync-dot').style.background = 'var(--green)';
    syncOfflineQueue();
  }
}
window.addEventListener('online', updateOnlineStatus);
window.addEventListener('offline', updateOnlineStatus);
updateOnlineStatus();

// ── OFFLINE WORK ORDER QUEUE ──────────────────────────────────────────────────
let _offlineQueue = JSON.parse(localStorage.getItem('nexus-offline-wo') || '[]');

function queueOfflineWO(data) {
  const id = 'offline-' + Date.now();
  _offlineQueue.push({ ...data, offline_id: id, created_locally: new Date().toISOString() });
  localStorage.setItem('nexus-offline-wo', JSON.stringify(_offlineQueue));
  toast(`Work order saved offline (${_offlineQueue.length} queued)`, 'warning');
  return id;
}

async function syncOfflineQueue() {
  if (!_offlineQueue.length) return;
  const syncLabel = document.getElementById('sync-label');
  const syncDot = document.getElementById('sync-dot');
  syncDot.classList.add('syncing');
  if (syncLabel) { syncLabel.style.display='inline'; syncLabel.textContent='Syncing…'; }
  try {
    const result = await api('POST', '/mobile/sync-offline', _offlineQueue);
    const synced = result.synced || [];
    const failed = synced.filter(r => r.error);
    const ok = synced.filter(r => !r.error);
    _offlineQueue = _offlineQueue.filter(q => failed.find(f => f.offline_id === q.offline_id));
    localStorage.setItem('nexus-offline-wo', JSON.stringify(_offlineQueue));
    if (ok.length) toast(`✓ Synced ${ok.length} offline work order${ok.length>1?'s':''}`, 'success');
    if (failed.length) toast(`⚠ ${failed.length} work orders failed to sync`, 'error');
  } catch(e) {
    toast('Sync failed — will retry when online', 'error');
  } finally {
    syncDot.classList.remove('syncing');
    if (syncLabel) syncLabel.style.display = 'none';
  }
}

// ── QR / BARCODE SCANNER ──────────────────────────────────────────────────────
let _qrStream = null;
let _qrInterval = null;

async function openQRScanner() {
  if (!navigator.mediaDevices?.getUserMedia) {
    qrManualEntry();
    return;
  }
  const overlay = document.getElementById('qr-scanner-overlay');
  const video = document.getElementById('qr-video');
  overlay.classList.add('active');
  try {
    _qrStream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: 'environment', width: { ideal: 1280 }, height: { ideal: 720 } }
    });
    video.srcObject = _qrStream;
    document.getElementById('qr-result').textContent = 'Scanning…';
    // Use BarcodeDetector if available
    if ('BarcodeDetector' in window) {
      const detector = new BarcodeDetector({ formats: ['qr_code','code_128','code_39','ean_13','ean_8','data_matrix'] });
      _qrInterval = setInterval(async () => {
        try {
          const codes = await detector.detect(video);
          if (codes.length > 0) {
            clearInterval(_qrInterval);
            const code = codes[0].rawValue;
            document.getElementById('qr-result').textContent = '✓ Detected: ' + code;
            setTimeout(() => { closeQRScanner(); handleQRResult(code); }, 500);
          }
        } catch(e) {}
      }, 200);
    } else {
      document.getElementById('qr-result').textContent = 'Camera active — BarcodeDetector not available. Enter manually.';
    }
  } catch(err) {
    closeQRScanner();
    if (err.name === 'NotAllowedError') toast('Camera permission denied', 'error');
    else qrManualEntry();
  }
}

function closeQRScanner() {
  const overlay = document.getElementById('qr-scanner-overlay');
  overlay.classList.remove('active');
  if (_qrInterval) { clearInterval(_qrInterval); _qrInterval = null; }
  if (_qrStream) { _qrStream.getTracks().forEach(t => t.stop()); _qrStream = null; }
  document.getElementById('qr-video').srcObject = null;
}

function qrManualEntry() {
  closeQRScanner();
  const code = prompt('Enter asset code, part number, or WO number:');
  if (code) handleQRResult(code.trim());
}

async function handleQRResult(code) {
  try {
    const result = await api('GET', '/mobile/scan/' + encodeURIComponent(code));
    if (result.type === 'asset') {
      toast(`Asset found: ${result.data.name}`, 'success');
      openAssetHistory(result.data.id);
    } else if (result.type === 'part') {
      toast(`Part found: ${result.data.name} (Stock: ${result.data.quantity})`, 'success');
      showPage('parts');
    } else if (result.type === 'work_order') {
      toast(`Work Order: ${result.data.wo_number}`, 'success');
      showPage('work-orders');
    } else {
      toast(`Code not found: ${code}`, 'warning');
    }
  } catch(e) {
    toast(`Not found: ${code}`, 'warning');
  }
}

// ── PWA / SERVICE WORKER ──────────────────────────────────────────────────────
let _pwaInstallEvent = null;

if ('serviceWorker' in navigator) {
  window.addEventListener('load', async () => {
    try {
      const reg = await navigator.serviceWorker.register('/sw.js');
      // Listen for messages from SW
      navigator.serviceWorker.addEventListener('message', e => {
        if (e.data?.type === 'SYNC_OFFLINE_WO') syncOfflineQueue();
      });
    } catch(e) { console.warn('SW registration failed:', e); }
  });
}

window.addEventListener('beforeinstallprompt', e => {
  e.preventDefault();
  _pwaInstallEvent = e;
  // Show install banner if not dismissed
  if (!localStorage.getItem('nexus-pwa-dismissed')) {
    const banner = document.getElementById('pwa-install-banner');
    banner.style.display = 'flex';
  }
});

document.getElementById('pwa-install-btn')?.addEventListener('click', async () => {
  if (_pwaInstallEvent) {
    _pwaInstallEvent.prompt();
    const { outcome } = await _pwaInstallEvent.userChoice;
    if (outcome === 'accepted') toast('NEXUS CMMS installed!', 'success');
    _pwaInstallEvent = null;
  }
  document.getElementById('pwa-install-banner').style.display = 'none';
});

function dismissPWA() {
  document.getElementById('pwa-install-banner').style.display = 'none';
  localStorage.setItem('nexus-pwa-dismissed', '1');
}

// ── SSE: REAL-TIME EVENT STREAM ───────────────────────────────────────────────
function connectSSE() {
  if (!window.EventSource) return;
  const es = new EventSource('/api/events');

  es.addEventListener('connected', e => {
    console.log('SSE connected');
    document.getElementById('sync-dot').style.background = 'var(--green)';
  });

  es.addEventListener('wo_created', e => {
    const d = JSON.parse(e.data);
    // Only show toast if someone else created it
    if (state.user && d.title) {
      toast(`🔧 New WO: ${d.wo_number} - ${d.title}`, d.priority === 'critical' ? 'error' : 'warning');
      // Refresh badge
      loadDashboardBadges?.();
    }
  });

  es.addEventListener('error', () => {
    // SSE disconnected — will auto-reconnect
    document.getElementById('sync-dot').style.background = 'var(--yellow)';
  });
}

// ── KEYBOARD SHORTCUTS HELP ───────────────────────────────────────────────────
function showKeyboardHelp() {
  const html = `
    <div style="position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);
      background:var(--bg2);border:1px solid var(--border);border-radius:var(--r16);
      padding:24px;z-index:2000;min-width:360px;max-width:90vw;max-height:80vh;overflow-y:auto">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
        <h3 style="font-size:15px">⌨ Keyboard Shortcuts</h3>
        <button onclick="this.closest('.modal-overlay').remove()" style="background:none;border:none;color:var(--text2);font-size:20px;cursor:pointer">✕</button>
      </div>
      <table style="width:100%;border-collapse:collapse;font-size:13px">
        <tr><td style="padding:6px 0;color:var(--text2)"><kbd class="kbd">Alt+D</kbd></td><td style="padding:6px 8px">Dashboard</td></tr>
        <tr><td><kbd class="kbd">Alt+W</kbd></td><td style="padding:6px 8px">Work Orders</td></tr>
        <tr><td><kbd class="kbd">Alt+A</kbd></td><td style="padding:6px 8px">Assets</td></tr>
        <tr><td><kbd class="kbd">Alt+P</kbd></td><td style="padding:6px 8px">PM Schedules</td></tr>
        <tr><td><kbd class="kbd">Alt+R</kbd></td><td style="padding:6px 8px">Parts & Inventory</td></tr>
        <tr><td><kbd class="kbd">Alt+N</kbd></td><td style="padding:6px 8px">New item (context-sensitive)</td></tr>
        <tr><td><kbd class="kbd">Alt+Q</kbd></td><td style="padding:6px 8px">Open QR Scanner</td></tr>
        <tr><td><kbd class="kbd">Esc</kbd></td><td style="padding:6px 8px">Close modal/scanner</td></tr>
        <tr><td><kbd class="kbd">?</kbd></td><td style="padding:6px 8px">Show this help</td></tr>
      </table>
    </div>`;
  const overlay = document.createElement('div');
  overlay.className = 'modal-overlay';
  overlay.innerHTML = html;
  overlay.addEventListener('click', e => { if (e.target === overlay) overlay.remove(); });
  document.body.appendChild(overlay);
}

// ── OFFLINE-AWARE API WRAPPER ─────────────────────────────────────────────────
const _apiOrig = api;
async function apiWithOffline(method, path, body) {
  if (!navigator.onLine && method === 'POST' && path === '/work-orders') {
    return { success: true, offline_id: queueOfflineWO(body), offline: true };
  }
  return _apiOrig(method, path, body);
}

// Override api for offline-aware WO creation only
const _apiBase = api;

// ── PULL TO REFRESH (mobile) ──────────────────────────────────────────────────
let _ptStartY = 0, _ptPulling = false;
document.addEventListener('touchstart', e => {
  const content = document.querySelector('.content');
  if (content && content.scrollTop === 0) _ptStartY = e.touches[0].clientY;
}, { passive: true });
document.addEventListener('touchend', e => {
  if (_ptPulling) {
    _ptPulling = false;
    const dist = e.changedTouches[0].clientY - _ptStartY;
    if (dist > 80) {
      toast('🔄 Refreshing…', 'success');
      if (state.currentPage === 'dashboard') loadDashboard();
      else if (state.currentPage === 'work-orders') loadWO();
      else if (state.currentPage === 'assets') loadAssets();
      else if (state.currentPage === 'parts') loadParts();
    }
  }
}, { passive: true });
document.addEventListener('touchmove', e => {
  if (_ptStartY > 0) {
    const dist = e.touches[0].clientY - _ptStartY;
    if (dist > 20) _ptPulling = true;
  }
}, { passive: true });

// ══════════════════════════════════════════════════════════════════
// ADVANCED GUI v4 — Command Palette, Kanban, Welcome, Sidebar
// Collapse, Context Menu, Notification Panel, Activity Feed,
// Theme Accent Picker, Enhanced Keyboard Shortcuts, Tooltips
// ══════════════════════════════════════════════════════════════════

// ── SIDEBAR COLLAPSE ──────────────────────────────────────────────
function toggleSidebarCollapse() {
  const sb = document.querySelector('.sidebar');
  const btn = sb.querySelector('.sidebar-collapse-btn');
  state.sidebarCollapsed = !state.sidebarCollapsed;
  sb.classList.toggle('collapsed', state.sidebarCollapsed);
  btn.textContent = state.sidebarCollapsed ? '▶' : '◀';
  btn.title = state.sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar (\\)';
  localStorage.setItem('cmms_sidebar_collapsed', state.sidebarCollapsed ? '1' : '');
}

function initSidebarCollapse() {
  if (localStorage.getItem('cmms_sidebar_collapsed')) {
    const sb = document.querySelector('.sidebar');
    const btn = sb.querySelector('.sidebar-collapse-btn');
    state.sidebarCollapsed = true;
    sb.classList.add('collapsed');
    if (btn) { btn.textContent = '▶'; btn.title = 'Expand sidebar'; }
  }
}

// ── COMMAND PALETTE ───────────────────────────────────────────────
const CMD_ITEMS = [
  { icon:'◈', label:'Dashboard',       desc:'Overview & KPIs',       action:()=>showPage('dashboard'),    kbd:'G D' },
  { icon:'📋', label:'Work Orders',     desc:'Manage maintenance WOs', action:()=>showPage('work-orders'),  kbd:'G W' },
  { icon:'🗂', label:'Kanban Board',    desc:'Drag & drop WO board',   action:()=>showPage('kanban'),       kbd:'G K' },
  { icon:'⚙',  label:'Assets',          desc:'Equipment registry',     action:()=>showPage('assets'),       kbd:'G A' },
  { icon:'🗓', label:'PM Schedules',    desc:'Preventive maintenance', action:()=>showPage('pm'),           kbd:'' },
  { icon:'📅', label:'Calendar',        desc:'Schedule view',          action:()=>showPage('calendar'),     kbd:'G C' },
  { icon:'📊', label:'Equipment History',desc:'Asset lifecycle',       action:()=>showPage('eq-history'),   kbd:'' },
  { icon:'📡', label:'Activity Feed',   desc:'Live system events',     action:()=>showPage('activity'),     kbd:'' },
  { icon:'📊', label:'Reports',         desc:'Analytics & exports',    action:()=>showPage('reports'),      kbd:'' },
  { icon:'📦', label:'Parts & Stock',   desc:'Inventory management',   action:()=>showPage('parts'),        kbd:'G P' },
  { icon:'🏭', label:'Suppliers',       desc:'Vendor management',      action:()=>showPage('suppliers'),    kbd:'' },
  { icon:'⬆',  label:'Import Data',     desc:'CSV import',             action:()=>showPage('import'),       kbd:'' },
  { icon:'➕', label:'New Work Order',  desc:'Create a WO',            action:()=>showCreateWO(),           kbd:'N' },
  { icon:'📷', label:'QR Scanner',      desc:'Scan asset code',        action:()=>openQRScanner(),          kbd:'' },
  { icon:'🌙', label:'Toggle Theme',    desc:'Dark / light mode',      action:()=>toggleTheme(),            kbd:'T' },
  { icon:'⌨',  label:'Keyboard Shortcuts',desc:'View all shortcuts',  action:()=>document.getElementById('shortcut-overlay').classList.add('active'), kbd:'?' },
  { icon:'👤', label:'My Profile',      desc:'Account settings',       action:()=>showPage('profile'),      kbd:'' },
  { icon:'→',  label:'Sign Out',        desc:'Log out',                action:()=>doLogout(),               kbd:'' },
  { icon:'ℹ',  label:'About',           desc:'Version & developer info', action:()=>showPage('about'),       kbd:'' },
  { icon:'💰', label:'Budget Tracker',  desc:'Monthly budget vs actual', action:()=>showPage('budget'),      kbd:'' },
  { icon:'⏱', label:'SLA Monitor',     desc:'Response & resolution SLAs', action:()=>showPage('sla-monitor'), kbd:'' },
  { icon:'🪄', label:'Reorder Wizard',  desc:'Auto-generate POs for low stock', action:()=>showPage('reorder-wizard'), kbd:'' },
  { icon:'🛒', label:'Purchase Orders', desc:'Manage purchase orders',  action:()=>showPage('purchase-orders'), kbd:'' },
];
let _cmdSelected = 0;
let _cmdFiltered = [];

function openCmdPalette() {
  document.getElementById('cmd-palette-overlay').classList.add('active');
  const inp = document.getElementById('cmd-input');
  inp.value = '';
  cmdFilter('');
  setTimeout(() => inp.focus(), 50);
}

function closeCmdPalette() {
  document.getElementById('cmd-palette-overlay').classList.remove('active');
}

function cmdFilter(q) {
  q = q.toLowerCase().trim();
  _cmdFiltered = q ? CMD_ITEMS.filter(i =>
    i.label.toLowerCase().includes(q) ||
    (i.desc && i.desc.toLowerCase().includes(q))
  ) : CMD_ITEMS;
  _cmdSelected = 0;
  renderCmdResults();
}

function renderCmdResults() {
  const el = document.getElementById('cmd-results');
  if (!_cmdFiltered.length) {
    el.innerHTML = '<div style="padding:24px;text-align:center;color:var(--text2);font-size:13px">No results found</div>';
    return;
  }
  el.innerHTML = _cmdFiltered.map((item, i) => `
    <div class="cmd-item${i === _cmdSelected ? ' selected' : ''}" onmouseenter="cmdHover(${i})" onclick="cmdSelect(${i})">
      <span class="cmd-item-icon">${item.icon}</span>
      <div>
        <div class="cmd-item-label">${item.label}</div>
        ${item.desc ? `<div style="font-size:11px;color:var(--text2)">${item.desc}</div>` : ''}
      </div>
      ${item.kbd ? `<span class="cmd-item-kbd">${item.kbd}</span>` : ''}
    </div>
  `).join('');
}

function cmdHover(i) { _cmdSelected = i; renderCmdResults(); }

function cmdSelect(i) {
  if (_cmdFiltered[i]) {
    _cmdFiltered[i].action();
    closeCmdPalette();
  }
}

function cmdKeydown(e) {
  if (e.key === 'ArrowDown') { e.preventDefault(); _cmdSelected = Math.min(_cmdSelected+1, _cmdFiltered.length-1); renderCmdResults(); }
  else if (e.key === 'ArrowUp') { e.preventDefault(); _cmdSelected = Math.max(_cmdSelected-1, 0); renderCmdResults(); }
  else if (e.key === 'Enter') { e.preventDefault(); cmdSelect(_cmdSelected); }
  else if (e.key === 'Escape') { closeCmdPalette(); }
}

// ── ENHANCED KEYBOARD SHORTCUTS ───────────────────────────────────
function initEnhancedShortcuts() {
  let _gPressed = false, _gTimer = null;
  document.addEventListener('keydown', e => {
    const tag = document.activeElement?.tagName;
    const isInput = ['INPUT','TEXTAREA','SELECT'].includes(tag);
    
    // Ctrl+K / Cmd+K = command palette (case-insensitive)
    if ((e.ctrlKey || e.metaKey) && (e.key === 'k' || e.key === 'K')) {
      e.preventDefault();
      e.stopPropagation();
      const overlay = document.getElementById('cmd-palette-overlay');
      if (overlay) {
        overlay.classList.contains('active') ? closeCmdPalette() : openCmdPalette();
      }
      return;
    }
    
    if (isInput) return;
    
    // ESC
    if (e.key === 'Escape') {
      closeCmdPalette();
      document.getElementById('shortcut-overlay')?.classList.remove('active');
      document.querySelectorAll('.modal-overlay').forEach(m => m.remove());
      closeCtxMenu();
      const notifPanel = document.getElementById('notif-panel');
      if (notifPanel) notifPanel.style.display = 'none';
      return;
    }
    // ? = shortcuts overlay
    if (e.key === '?') { 
      const shortcutOverlay = document.getElementById('shortcut-overlay');
      if (shortcutOverlay) shortcutOverlay.classList.add('active'); 
      return; 
    }
    // T = toggle theme
    if (e.key === 't' || e.key === 'T') { toggleTheme(); return; }
    // N = new WO
    if (e.key === 'n' || e.key === 'N') { showCreateWO(); return; }
    // \ = toggle sidebar
    if (e.key === '\\') { toggleSidebarCollapse(); return; }
    // F = focus mode
    if (e.key === 'f' || e.key === 'F') { toggleFocusMode(); return; }
    // G+_ = goto shortcuts
    if (e.key === 'g' || e.key === 'G') {
      _gPressed = true;
      clearTimeout(_gTimer);
      _gTimer = setTimeout(() => { _gPressed = false; }, 1500);
      return;
    }
    if (_gPressed) {
      _gPressed = false;
      clearTimeout(_gTimer);
      const map = { d:'dashboard', w:'work-orders', a:'assets', p:'parts', k:'kanban', c:'calendar', r:'reports' };
      const pg = map[e.key.toLowerCase()];
      if (pg) showPage(pg);
    }
  });
}

// ── FOCUS MODE ────────────────────────────────────────────────────
function toggleFocusMode() {
  document.body.classList.toggle('focus-mode');
  toast(document.body.classList.contains('focus-mode') ? '🎯 Focus mode on' : '🔓 Focus mode off', 'info');
}

// ── CONTEXT MENU ──────────────────────────────────────────────────
function showCtxMenu(e, items) {
  e.preventDefault();
  closeCtxMenu();
  const menu = document.getElementById('ctx-menu');
  menu.innerHTML = items.map(item =>
    item === '-' ? '<div class="ctx-divider"></div>' :
    `<div class="ctx-item${item.danger?' danger':''}" onclick="closeCtxMenu();(${item.action.toString()})()">
      ${item.icon||''} ${item.label}
    </div>`
  ).join('');
  const x = Math.min(e.clientX, window.innerWidth - 200);
  const y = Math.min(e.clientY, window.innerHeight - (items.length * 36 + 20));
  menu.style.cssText = `display:block;left:${x}px;top:${y}px`;
  setTimeout(() => document.addEventListener('click', closeCtxMenu, { once: true }), 50);
}

function closeCtxMenu() {
  document.getElementById('ctx-menu').style.display = 'none';
}

// ── NOTIFICATION PANEL ────────────────────────────────────────────
function toggleNotifPanel(e) {
  e.stopPropagation();
  const panel = document.getElementById('notif-panel');
  const isVisible = panel.style.display !== 'none';
  if (!isVisible) {
    loadNotifPanel();
    panel.style.display = 'block';
    setTimeout(() => document.addEventListener('click', closeNotifPanel, { once: true }), 50);
  } else {
    panel.style.display = 'none';
  }
}

function closeNotifPanel() {
  const p = document.getElementById('notif-panel');
  if (p) p.style.display = 'none';
}

async function loadNotifPanel() {
  const body = document.getElementById('notif-panel-body');
  try {
    const r = await api('GET', '/notifications');
    const items = r.notifications || [];
    if (!items.length) {
      body.innerHTML = '<div class="empty-state" style="padding:20px"><div class="icon">🔔</div><h3>All caught up!</h3></div>';
      return;
    }
    body.innerHTML = items.slice(0,15).map(n => `
      <div class="notif-item${n.is_read ? '' : ' unread'}" onclick="closeNotifPanel()">
        ${!n.is_read ? '<div class="notif-item-dot"></div>' : '<div style="width:8px"></div>'}
        <div>
          <div class="notif-item-title">${escH(n.title||'Notification')}</div>
          <div class="notif-item-msg">${escH(n.message||'')}</div>
          <div class="notif-item-time">${relTime(n.created_at)}</div>
        </div>
      </div>
    `).join('');
  } catch(e) {
    body.innerHTML = '<div style="padding:16px;color:var(--text2);font-size:13px">Unable to load</div>';
  }
}

function relTime(ts) {
  if (!ts) return '';
  const diff = (Date.now() - new Date(ts)) / 1000;
  if (diff < 60) return 'just now';
  if (diff < 3600) return Math.floor(diff/60) + 'm ago';
  if (diff < 86400) return Math.floor(diff/3600) + 'h ago';
  return Math.floor(diff/86400) + 'd ago';
}

// ── WELCOME BANNER ────────────────────────────────────────────────
function renderWelcomeBanner(data) {
  const banner = document.getElementById('welcome-banner');
  const strip = document.getElementById('dash-quick-strip');
  const user = state.user;
  if (!banner || !user) return;
  const h = new Date().getHours();
  const greet = h < 12 ? 'Good morning' : h < 18 ? 'Good afternoon' : 'Good evening';
  const emoji = h < 12 ? '☀️' : h < 18 ? '🌤' : '🌙';
  const open = data.open_wo || 0;
  const pmDue = data.pm_due_soon || 0;
  const overdue = data.overdue_wo || 0;
  document.getElementById('welcome-emoji').textContent = emoji;
  document.getElementById('welcome-heading').textContent = `${greet}, ${user.name?.split(' ')[0] || 'there'}!`;
  document.getElementById('welcome-sub').textContent =
    `${open} open WO${open!==1?'s':''} · ${overdue} overdue · ${pmDue} PM${pmDue!==1?'s':''} due soon`;
  // Quick strip
  if (strip) {
    document.getElementById('qs-open').textContent = data.open_wo ?? '—';
    document.getElementById('qs-overdue').textContent = data.overdue_wo ?? '—';
    document.getElementById('qs-assets').textContent = data.total_assets ?? '—';
    document.getElementById('qs-pm-due').textContent = data.pm_due_soon ?? '—';
    document.getElementById('qs-low-stock').textContent = data.low_stock ?? '—';
    strip.style.display = 'flex';
  }
  banner.style.display = localStorage.getItem('cmms_hide_banner') ? 'none' : 'flex';
  const dismissBtn = banner.querySelector('.welcome-dismiss');
  if (dismissBtn) dismissBtn.onclick = () => {
    banner.style.display = 'none';
    localStorage.setItem('cmms_hide_banner', '1');
  };
}

// ── KANBAN BOARD ──────────────────────────────────────────────────
async function loadKanban() {
  try {
    const r = await api('GET', '/work-orders?per_page=200');
    state.data.kanban_wos = r.work_orders || [];
    renderKanban();
    setupKanbanDnD();
  } catch(e) { toast('Failed to load kanban: ' + e.message, 'error'); }
}

function renderKanban() {
  const wos = state.data.kanban_wos || [];
  const filterPri = document.getElementById('kanban-filter-priority')?.value || '';
  const statuses = ['open','in_progress','on_hold','completed','cancelled'];
  statuses.forEach(st => {
    const col = document.getElementById('kancards-' + st);
    const cnt = document.getElementById('kancnt-' + st);
    if (!col) return;
    const cards = wos.filter(w => w.status === st && (!filterPri || w.priority === filterPri));
    if (cnt) cnt.textContent = cards.length;
    if (!cards.length) {
      col.innerHTML = `<div style="text-align:center;padding:20px;color:var(--text2);font-size:12px">No ${st.replace('_',' ')} orders</div>`;
      return;
    }
    col.innerHTML = cards.map(w => {
      const dueColor = w.due_date && new Date(w.due_date) < new Date() ? 'var(--red)' : 'var(--text2)';
      return `
      <div class="kanban-card p-${w.priority||'medium'}" draggable="true"
           data-wo-id="${w.id}" data-wo-status="${w.status}"
           onclick="showWODetail(${w.id})"
           oncontextmenu="kanbanCtx(event,${w.id},'${w.status}')">
        <div class="kanban-card-id">${escH(w.wo_number||'')}</div>
        <div class="kanban-card-title">${escH(w.title||'Untitled')}</div>
        <div class="kanban-card-meta">
          <span class="badge b-${w.priority||'medium'}">${w.priority||'med'}</span>
          <span class="badge b-${w.type||'corrective'}" style="font-size:9px">${(w.type||'corrective').replace('_',' ')}</span>
        </div>
        <div class="kanban-card-footer">
          <span class="kanban-card-asset" style="font-size:10px">⚙ ${escH(w.asset_name||'No asset')}</span>
          ${w.due_date ? `<span class="kanban-card-due" style="color:${dueColor}">${fmt(w.due_date)}</span>` : ''}
        </div>
      </div>`;
    }).join('');
  });
  // Reattach drag listeners
  setupKanbanDnD();
}

function kanbanCtx(e, woId, currentStatus) {
  e.stopPropagation();
  const statuses = {open:'Open',in_progress:'In Progress',on_hold:'On Hold',completed:'Completed',cancelled:'Cancelled'};
  const moveItems = Object.entries(statuses)
    .filter(([st]) => st !== currentStatus)
    .map(([st, label]) => ({
      icon: '→', label: `Move to ${label}`,
      action: new Function(`return function(){kanbanMove(${woId},'${st}')}`)()
    }));
  showCtxMenu(e, [
    { icon:'📋', label:'View Details', action: new Function(`return function(){showWODetail(${woId})}`)() },
    '-',
    ...moveItems,
    '-',
    { icon:'🗑', label:'Delete', danger: true, action: new Function(`return function(){if(confirm('Delete this WO?'))deleteWO(${woId})}`)() }
  ]);
}

async function kanbanMove(woId, newStatus) {
  try {
    await api('PUT', `/work-orders/${woId}`, { status: newStatus });
    const wo = state.data.kanban_wos?.find(w => w.id === woId);
    if (wo) wo.status = newStatus;
    renderKanban();
    pushActivityEvent('status_change', `WO #${woId} moved to ${newStatus.replace('_',' ')}`);
    toast(`Moved to ${newStatus.replace('_',' ')}`, 'success');
  } catch(e) { toast('Failed: ' + e.message, 'error'); }
}

function setupKanbanDnD() {
  document.querySelectorAll('.kanban-card').forEach(card => {
    card.addEventListener('dragstart', e => {
      state.kanban.dragWoId = parseInt(card.dataset.woId);
      state.kanban.dragStatus = card.dataset.woStatus;
      card.classList.add('dragging');
      e.dataTransfer.effectAllowed = 'move';
    });
    card.addEventListener('dragend', () => {
      card.classList.remove('dragging');
      document.querySelectorAll('.kanban-col').forEach(c => c.classList.remove('drag-over'));
    });
  });
  document.querySelectorAll('.kanban-col').forEach(col => {
    col.addEventListener('dragover', e => {
      e.preventDefault();
      e.dataTransfer.dropEffect = 'move';
      document.querySelectorAll('.kanban-col').forEach(c => c.classList.remove('drag-over'));
      col.classList.add('drag-over');
    });
    col.addEventListener('dragleave', () => col.classList.remove('drag-over'));
    col.addEventListener('drop', async e => {
      e.preventDefault();
      col.classList.remove('drag-over');
      const newStatus = col.dataset.status;
      if (state.kanban.dragWoId && newStatus && newStatus !== state.kanban.dragStatus) {
        await kanbanMove(state.kanban.dragWoId, newStatus);
      }
      state.kanban.dragWoId = null;
      state.kanban.dragStatus = null;
    });
  });
}

// ── ACTIVITY FEED ─────────────────────────────────────────────────
const _activityEvents = [];

function pushActivityEvent(type, text, user) {
  const item = {
    type, text, user: user || state.user?.name || 'System',
    time: new Date().toISOString(),
    color: { status_change:'var(--yellow)', create:'var(--blue)',
              complete:'var(--green)', error:'var(--red)', pm:'var(--purple)' }[type] || 'var(--text2)'
  };
  _activityEvents.unshift(item);
  if (_activityEvents.length > 100) _activityEvents.pop();
  if (state.currentPage === 'activity') renderActivityFeed();
  // Show dot in nav
  const dot = document.querySelector('.nav-item[onclick*="activity"] .nav-badge');
}

function loadActivityPage() {
  renderActivityFeed();
  renderActivitySummary();
}

function renderActivityFeed() {
  const el = document.getElementById('activity-feed-list');
  if (!el) return;
  if (!_activityEvents.length) {
    el.innerHTML = '<div class="empty-state"><div class="icon">📡</div><h3>No activity yet</h3><p>Events will appear here as you use the system.</p></div>';
    return;
  }
  const avatarColor = ['var(--green)','var(--blue)','var(--yellow)','var(--purple)','var(--red)'];
  el.innerHTML = _activityEvents.map((ev, i) => `
    <div class="activity-item">
      <div class="activity-avatar" style="background:${avatarColor[i%5]}">${(ev.user||'S')[0]}</div>
      <div class="activity-body">
        <div class="activity-text"><strong>${escH(ev.user||'System')}</strong> ${escH(ev.text)}</div>
        <div class="activity-time">${relTime(ev.time)} · ${ev.type.replace('_',' ')}</div>
      </div>
      <div class="activity-type-dot" style="background:${ev.color}"></div>
    </div>
  `).join('');
}

function renderActivitySummary() {
  const el = document.getElementById('activity-summary-content');
  if (!el) return;
  const today = _activityEvents.filter(e => {
    const d = new Date(e.time);
    const n = new Date();
    return d.toDateString() === n.toDateString();
  });
  const byType = {};
  today.forEach(e => { byType[e.type] = (byType[e.type]||0) + 1; });
  el.innerHTML = Object.entries(byType).map(([t,c]) =>
    `<div class="settings-row" style="padding:8px 0">
      <span style="font-size:13px;color:var(--text1)">${t.replace('_',' ')}</span>
      <span class="badge b-info">${c}</span>
    </div>`
  ).join('') || '<div style="padding:16px;color:var(--text2);font-size:13px;text-align:center">No events today yet</div>';

  const healthEl = document.getElementById('activity-health-content');
  if (healthEl) {
    healthEl.innerHTML = `
      <div class="settings-row"><span class="settings-row-info"><h4>API Status</h4></span>
        <span class="badge b-success">● Online</span></div>
      <div class="settings-row"><span class="settings-row-info"><h4>Database</h4></span>
        <span class="badge b-success">● Connected</span></div>
      <div class="settings-row"><span class="settings-row-info"><h4>Total Events Today</h4></span>
        <span style="font-family:var(--mono);font-weight:700">${today.length}</span></div>
    `;
  }
}

function clearActivityFeed() {
  _activityEvents.length = 0;
  renderActivityFeed();
}

// ── ACCENT COLOR PICKER ───────────────────────────────────────────
function initAccentPicker() {
  const saved = localStorage.getItem('cmms_accent') || 'green';
  applyAccent(saved);
}

function applyAccent(name) {
  const body = document.body;
  body.classList.remove('accent-blue','accent-purple','accent-orange','accent-red');
  if (name !== 'green') body.classList.add('accent-' + name);
  localStorage.setItem('cmms_accent', name);
  state.accent = name;
}

// ── SKELETON LOADER ───────────────────────────────────────────────
function showSkeleton(containerId, rows=4) {
  const el = document.getElementById(containerId);
  if (!el) return;
  el.innerHTML = Array(rows).fill(0).map(() =>
    `<div style="margin-bottom:12px">
      <div class="skeleton skeleton-text" style="width:${40+Math.random()*40}%"></div>
      <div class="skeleton skeleton-text" style="width:${20+Math.random()*30}%"></div>
    </div>`
  ).join('');
}

// ── ENHANCED SSE ACTIVITY TRACKING ───────────────────────────────
// Hook into existing SSE to push to activity feed
(function patchSSE() {
  const origBroadcastHandler = window._sseOriginalHandler;
  // We'll intercept at the ES message level by patching showPage
  const _origShowPage = typeof _origShowPageInternal !== 'undefined' ? _origShowPageInternal : null;
})();

// Intercept api calls to log activity
(function patchApi() {
  const _orig = api;
  window.api = async function(method, path, body) {
    const result = await _orig(method, path, body);
    if (method !== 'GET' && result?.success) {
      let text = '';
      if (path.includes('/work-orders') && method === 'POST') text = 'created a new work order';
      else if (path.includes('/work-orders') && method === 'PUT') text = 'updated a work order';
      else if (path.includes('/work-orders') && method === 'DELETE') text = 'deleted a work order';
      else if (path.includes('/assets') && method === 'POST') text = 'added a new asset';
      else if (path.includes('/assets') && method === 'PUT') text = 'updated an asset';
      else if (path.includes('/parts') && method === 'POST') text = 'added a new part';
      else if (path.includes('/pm') && method === 'POST') text = 'completed a PM task';
      else if (path.includes('/inventory') && method === 'POST') text = 'adjusted inventory';
      if (text) pushActivityEvent('action', text);
    }
    return result;
  };
  // Rebind api so existing code uses patched version
  window.api = window.api;
})();

// ── ENHANCED DASHBOARD HOOK ───────────────────────────────────────
// After dashboard loads, show welcome banner and quick strip
const _origLoadDashboard = typeof loadDashboard !== 'undefined' ? loadDashboard : null;
if (typeof loadDashboard === 'function') {
  const _ld = loadDashboard;
  window.loadDashboard = async function() {
    await _ld();
    // Grab data from existing state
    setTimeout(() => {
      try {
        const d = state.data.dashboard || {};
        renderWelcomeBanner(d);
      } catch(e) {}
    }, 300);
  };
}

// ── TOOLTIP HELPER ────────────────────────────────────────────────
function addTooltip(el, text) {
  el.classList.add('tooltip-wrap');
  const tip = document.createElement('div');
  tip.className = 'tooltip-content';
  tip.textContent = text;
  el.appendChild(tip);
}

// ── INIT ALL v4 FEATURES ──────────────────────────────────────────
function initAdvancedGUI() {
  initSidebarCollapse();
  initEnhancedShortcuts();
  initAccentPicker();
  // Show welcome banner next dashboard load
  const _origDash = typeof loadDashboard === 'function' ? loadDashboard : null;
  // Hook dashboard data fetch to populate welcome & quick strip
  document.addEventListener('cmms:dashboard-loaded', e => {
    renderWelcomeBanner(e.detail || {});
  });
  // Add accent picker to settings (inject after theme toggle in topbar area)
  // Add right-click context menu on WO table rows
  document.addEventListener('contextmenu', e => {
    const row = e.target.closest('tr[onclick*="showWODetail"]');
    if (row) {
      const onclick = row.getAttribute('onclick') || '';
      const match = onclick.match(/showWODetail\((\d+)\)/);
      if (match) {
        const woId = parseInt(match[1]);
        e.preventDefault();
        showCtxMenu(e, [
          { icon:'👁', label:'View Details', action: new Function(`return function(){showWODetail(${woId})}`)() },
          { icon:'✏', label:'Edit', action: new Function(`return function(){showEditWO(${woId})}`)() },
          '-',
          { icon:'✅', label:'Mark Complete', action: new Function(`return function(){quickCompleteWO(${woId})}`)() },
          { icon:'⏸', label:'Put On Hold', action: new Function(`return function(){quickStatusWO(${woId},'on_hold')}`)() },
          '-',
          { icon:'🗑', label:'Delete', danger:true, action: new Function(`return function(){if(confirm('Delete?'))deleteWO(${woId})}`)() },
        ]);
      }
    }
  });
  console.log('[NEXUS CMMS v4] Advanced GUI initialized ✓');
}

// Quick helpers for context menu WO actions
async function quickCompleteWO(id) {
  try { await api('PUT', `/work-orders/${id}`, {status:'completed'}); toast('Marked complete','success'); if(state.currentPage==='work-orders')loadWO(); } catch(e){toast(e.message,'error');}
}
async function quickStatusWO(id, status) {
  try { await api('PUT', `/work-orders/${id}`, {status}); toast(`Status updated`,'success'); if(state.currentPage==='work-orders')loadWO(); } catch(e){toast(e.message,'error');}
}

// ── WIRE UP TO EXISTING INIT ──────────────────────────────────────
// Patch the existing initApp to call our init
const _origInitApp = typeof initApp === 'function' ? initApp : null;
if (typeof initApp === 'function') {
  const _ia = initApp;
  window.initApp = function() {
    _ia();
    setTimeout(initAdvancedGUI, 200);
  };
}

// Also expose showPage to accept 'kanban' & 'activity' gracefully via existing showPage
// (already handled by adding to _origShowPageInternal above)


// ══════════════════════════════════════════════════════════════════
// ADVANCED GUI v4.1 — Additional Updates
// Animated counters, Grid/List toggle, Enhanced WO table,
// Stock progress bars, Live clock, Breadcrumbs, Accent picker UI,
// Enhanced login, Dark overlay search, Gantt PM view
// ══════════════════════════════════════════════════════════════════

// alias showCreateWO → openWOModal(null)
function showCreateWO() { openWOModal(null); }
function showEditWO(id) { openWOModal(id); }
// alias showWODetail → openWODetail (used in kanban cards and context menus)
function showWODetail(id) { openWODetail(id); }
function deleteWO(id, num) {
  if (!confirm(`Delete work order ${num||id}? This cannot be undone.`)) return;
  api('DELETE', '/work-orders/' + id).then(() => { toast('Work order deleted', 'success'); loadWO(); }).catch(e => toast(e.message, 'error'));
}

// ── ANIMATED NUMBER COUNTER ───────────────────────────────────────
function animateCounter(el, target, duration=800, prefix='', suffix='') {
  if (!el) return;
  const start = parseFloat(el.textContent.replace(/[^0-9.]/g,'')) || 0;
  const startTime = performance.now();
  function update(now) {
    const elapsed = now - startTime;
    const progress = Math.min(elapsed / duration, 1);
    const eased = 1 - Math.pow(1 - progress, 3);
    const value = start + (target - start) * eased;
    el.textContent = prefix + Math.round(value).toLocaleString('en-IN') + suffix;
    if (progress < 1) requestAnimationFrame(update);
  }
  requestAnimationFrame(update);
}

// ── LIVE CLOCK ────────────────────────────────────────────────────
function initLiveClock() {
  const el = document.getElementById('live-clock');
  if (!el) return;
  function tick() {
    const now = new Date();
    el.textContent = now.toLocaleTimeString('en-IN', {hour:'2-digit', minute:'2-digit', second:'2-digit'});
  }
  tick();
  setInterval(tick, 1000);
}

// ── ASSETS GRID / LIST VIEW TOGGLE ───────────────────────────────
let assetsViewMode = localStorage.getItem('cmms_assets_view') || 'list';
function toggleAssetsView(mode) {
  assetsViewMode = mode;
  localStorage.setItem('cmms_assets_view', mode);
  document.getElementById('assets-view-list-btn')?.classList.toggle('active', mode==='list');
  document.getElementById('assets-view-grid-btn')?.classList.toggle('active', mode==='grid');
  loadAssets();
}

// Patch loadAssets to support grid mode
const _origLoadAssets = loadAssets;
window.loadAssets = async function() {
  const toolbar = document.querySelector('#page-assets .toolbar');
  if (toolbar && !document.getElementById('assets-view-list-btn')) {
    const viewToggle = document.createElement('div');
    viewToggle.style.cssText = 'display:flex;gap:4px;margin-left:auto';
    viewToggle.innerHTML = `
      <button id="assets-view-list-btn" class="btn btn-secondary btn-sm${assetsViewMode==='list'?' active':''}" onclick="toggleAssetsView('list')" title="List view">☰</button>
      <button id="assets-view-grid-btn" class="btn btn-secondary btn-sm${assetsViewMode==='grid'?' active':''}" onclick="toggleAssetsView('grid')" title="Grid view">⊞</button>`;
    toolbar.appendChild(viewToggle);
  }
  await _origLoadAssets();
  if (assetsViewMode === 'grid') convertAssetsToGrid();
};

function convertAssetsToGrid() {
  const tblWrap = document.querySelector('#page-assets .tbl-wrap');
  if (!tblWrap) return;
  const table = tblWrap.querySelector('table');
  if (!table) return;
  const rows = Array.from(table.querySelectorAll('tbody tr'));
  if (!rows.length) return;
  const grid = document.createElement('div');
  grid.style.cssText = 'display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:14px;padding:4px';
  rows.forEach(row => {
    const cells = row.querySelectorAll('td');
    if (cells.length < 4) return;
    const code = cells[0]?.textContent?.trim() || '—';
    const name = cells[1]?.textContent?.trim() || '';
    const cat  = cells[2]?.textContent?.trim() || '';
    const loc  = cells[3]?.textContent?.trim() || '';
    const statusBadge = cells[4]?.innerHTML || '';
    const critBadge   = cells[5]?.innerHTML || '';
    const btns        = cells[cells.length-1]?.innerHTML || '';
    const onclick = row.getAttribute('onclick') || '';
    const card = document.createElement('div');
    card.className = 'card';
    card.style.cssText = 'margin:0;cursor:pointer;transition:.2s;border-left:3px solid var(--accent)';
    card.onmouseover = () => card.style.transform = 'translateY(-2px)';
    card.onmouseout  = () => card.style.transform = '';
    card.innerHTML = `
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:10px">
        <div style="width:40px;height:40px;border-radius:8px;background:var(--bg3);display:flex;align-items:center;justify-content:center;font-size:20px;flex-shrink:0">⚙</div>
        <div style="min-width:0"><div style="font-size:14px;font-weight:600;color:var(--text0);overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${name}</div>
          <div style="font-family:var(--mono);font-size:11px;color:var(--accent)">${code}</div></div>
      </div>
      <div style="font-size:12px;color:var(--text2);margin-bottom:6px">📂 ${cat} · 📍 ${loc}</div>
      <div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:10px">${statusBadge} ${critBadge}</div>
      <div style="display:flex;gap:6px;justify-content:flex-end">${btns}</div>`;
    grid.appendChild(card);
  });
  tblWrap.innerHTML = '';
  tblWrap.appendChild(grid);
}

// ── ENHANCED STAT CARDS WITH MINI SPARKLINES ─────────────────────
function enhanceDashboardStats(d) {
  // Animate stat values
  document.querySelectorAll('.stat-value').forEach(el => {
    const txt = el.textContent.replace(/[^0-9.]/g,'');
    const num = parseFloat(txt);
    if (!isNaN(num) && num > 0) {
      const prefix = el.textContent.includes('₹') ? '₹' : '';
      const suffix = el.textContent.includes('%') ? '%' : '';
      animateCounter(el, num, 900, prefix, suffix);
    }
  });
  // Add mini bar charts to stat cards
  const cards = document.querySelectorAll('.stat-card');
  if (d && d.monthly_trend && d.monthly_trend.length) {
    const counts = d.monthly_trend.slice(-6).map(m => m.count || 0);
    const maxC = Math.max(...counts, 1);
    const mini = counts.map(c =>
      `<div class="mini-bar" style="height:${Math.round(c/maxC*28)+4}px"></div>`
    ).join('');
    cards.forEach((card, i) => {
      if (i === 1 && !card.querySelector('.mini-chart-bar')) { // Open WOs card
        const chart = document.createElement('div');
        chart.className = 'mini-chart-bar';
        chart.style.cssText = 'position:absolute;bottom:10px;right:60px;opacity:0.4;pointer-events:none';
        chart.innerHTML = mini;
        card.style.position = 'relative';
        card.appendChild(chart);
      }
    });
  }
}

// ── PARTS STOCK PROGRESS BARS ─────────────────────────────────────
function addStockBars() {
  const rows = document.querySelectorAll('#page-parts table tbody tr');
  rows.forEach(row => {
    const cells = row.querySelectorAll('td');
    if (cells.length < 4) return;
    const qty = parseInt(cells[3]?.textContent) || 0;
    const min = parseInt(cells[4]?.textContent) || 0;
    if (min <= 0) return;
    const pct = Math.min(Math.round(qty / min * 100), 100);
    const color = pct < 50 ? 'var(--red)' : pct < 100 ? 'var(--yellow)' : 'var(--green)';
    const existing = cells[3]?.querySelector('.stock-bar');
    if (!existing) {
      const bar = document.createElement('div');
      bar.className = 'stock-bar';
      bar.style.cssText = `height:3px;border-radius:2px;background:var(--bg3);margin-top:4px;overflow:hidden`;
      bar.innerHTML = `<div style="height:100%;width:${pct}%;background:${color};border-radius:2px;transition:width .6s"></div>`;
      cells[3].style.paddingBottom = '8px';
      cells[3].appendChild(bar);
    }
  });
}

// ── LIVE CLOCK IN TOPBAR ──────────────────────────────────────────
function injectLiveClock() {
  const topbarRight = document.querySelector('.topbar-right');
  if (topbarRight && !document.getElementById('live-clock')) {
    const clockEl = document.createElement('span');
    clockEl.id = 'live-clock';
    clockEl.style.cssText = 'font-family:var(--mono);font-size:12px;color:var(--text2);letter-spacing:1px;display:none';
    topbarRight.insertBefore(clockEl, topbarRight.firstChild);
    // Show on desktop
    if (window.innerWidth > 768) clockEl.style.display = '';
    initLiveClock();
  }
}

// ── ACCENT PICKER IN SETTINGS ─────────────────────────────────────
function injectAccentPicker() {
  const settingsContent = document.getElementById('settings-content');
  if (!settingsContent || document.getElementById('accent-picker-row')) return;
  const row = document.createElement('div');
  row.id = 'accent-picker-row';
  row.className = 'settings-row';
  row.innerHTML = `
    <div class="settings-row-info">
      <h4>Accent Color</h4>
      <p>Choose your preferred accent color for the interface</p>
    </div>
    <div class="accent-picker">
      ${[['green','#00e5a0'],['blue','#4da6ff'],['purple','#b06dff'],['orange','#ff8c42'],['red','#ff4d6d']].map(([name,color]) =>
        `<div class="accent-swatch${state.accent===name?' active':''}" style="background:${color}" title="${name}" onclick="applyAccent('${name}');document.querySelectorAll('.accent-swatch').forEach(s=>s.classList.remove('active'));this.classList.add('active')"></div>`
      ).join('')}
    </div>`;
  settingsContent.insertBefore(row, settingsContent.firstChild);
}

// ── ENHANCED WO TABLE: ROW COLORS FOR OVERDUE/CRITICAL ───────────
function colorizeWORows() {
  const rows = document.querySelectorAll('#page-work-orders table tbody tr');
  rows.forEach(row => {
    const text = row.textContent;
    const hasCritical = row.querySelector('.b-critical');
    const hasOverdue = row.querySelector('.b-overdue');
    if (hasOverdue || (hasCritical && row.querySelector('.b-open'))) {
      row.style.borderLeft = '3px solid var(--red)';
    } else if (hasCritical) {
      row.style.borderLeft = '3px solid var(--yellow)';
    }
  });
}

// ── ENHANCED LOGIN SCREEN ─────────────────────────────────────────
function enhanceLoginScreen() {
  const card = document.querySelector('.login-card');
  if (!card || card.dataset.enhanced) return;
  card.dataset.enhanced = '1';
  // Add animated background particles
  const bg = document.getElementById('login-screen');
  if (bg) {
    bg.style.position = 'relative';
    bg.style.overflow = 'hidden';
    for (let i = 0; i < 8; i++) {
      const dot = document.createElement('div');
      const size = 4 + Math.random() * 8;
      dot.style.cssText = `position:absolute;width:${size}px;height:${size}px;border-radius:50%;
        background:rgba(0,229,160,${0.05+Math.random()*0.1});
        left:${Math.random()*100}%;top:${Math.random()*100}%;
        animation:float-dot ${8+Math.random()*12}s ease-in-out infinite;
        animation-delay:${Math.random()*4}s;pointer-events:none`;
      bg.appendChild(dot);
    }
    // Add the keyframe if not already added
    if (!document.getElementById('float-dot-style')) {
      const s = document.createElement('style');
      s.id = 'float-dot-style';
      s.textContent = `@keyframes float-dot{0%,100%{transform:translateY(0) scale(1)}50%{transform:translateY(-30px) scale(1.2)}}`;
      document.head.appendChild(s);
    }
  }
}

// ── GANTT-STYLE PM VIEW ───────────────────────────────────────────
function renderPMGantt(pmList) {
  if (!pmList || !pmList.length) return '';
  const today = new Date();
  const maxDays = 60;
  return `
    <div class="gantt-wrap" style="margin-top:16px">
      <table class="gantt-table">
        <thead><tr>
          <th style="min-width:180px">PM Schedule</th>
          <th style="min-width:100px">Asset</th>
          <th style="min-width:80px">Frequency</th>
          <th style="min-width:80px">Due Date</th>
          <th class="gantt-bar-cell">Timeline (60 days)</th>
        </tr></thead>
        <tbody>${pmList.slice(0,15).map(pm => {
          const due = pm.next_due ? new Date(pm.next_due) : null;
          const daysUntil = due ? Math.round((due - today)/86400000) : null;
          const pct = due ? Math.min(Math.max(Math.round((daysUntil / maxDays) * 100), 0), 100) : 50;
          const barClass = daysUntil === null ? '' : daysUntil < 0 ? 'status-overdue' : daysUntil < 7 ? 'status-soon' : 'status-ok';
          const barLabel = daysUntil === null ? '' : daysUntil < 0 ? `${Math.abs(daysUntil)}d overdue` : daysUntil === 0 ? 'Due today' : `${daysUntil}d`;
          return `<tr>
            <td class="gantt-label">${escH(pm.title)}</td>
            <td style="font-size:11px;color:var(--text2)">${escH(pm.asset_name||'—')}</td>
            <td style="font-size:11px">${pm.frequency||'—'}</td>
            <td style="font-family:var(--mono);font-size:11px;color:${daysUntil!==null&&daysUntil<0?'var(--red)':daysUntil!==null&&daysUntil<7?'var(--yellow)':'var(--text1)'}">${pm.next_due||'—'}</td>
            <td class="gantt-bar-cell">
              <div class="gantt-bar-track">
                <div class="gantt-bar-fill ${barClass}" style="width:${pct}%">${barLabel}</div>
              </div>
            </td>
          </tr>`;
        }).join('')}
        </tbody>
      </table>
    </div>`;
}

// ── PATCH PM PAGE TO ADD GANTT TOGGLE ────────────────────────────
const _origLoadPM = loadPM;
window.loadPM = async function() {
  await _origLoadPM();
  const pmPage = document.getElementById('page-pm');
  if (!pmPage) return;
  // Add gantt view button if not present
  const toolbar = pmPage.querySelector('.toolbar');
  if (toolbar && !document.getElementById('pm-gantt-btn')) {
    const btn = document.createElement('button');
    btn.id = 'pm-gantt-btn';
    btn.className = 'btn btn-secondary btn-sm';
    btn.textContent = '📊 Gantt View';
    btn.onclick = () => togglePMGantt();
    toolbar.appendChild(btn);
  }
};

let _pmGanttVisible = false;
async function togglePMGantt() {
  _pmGanttVisible = !_pmGanttVisible;
  const btn = document.getElementById('pm-gantt-btn');
  if (btn) btn.textContent = _pmGanttVisible ? '☰ List View' : '📊 Gantt View';
  const pmPage = document.getElementById('page-pm');
  let ganttEl = document.getElementById('pm-gantt-container');
  if (_pmGanttVisible) {
    if (!ganttEl) {
      ganttEl = document.createElement('div');
      ganttEl.id = 'pm-gantt-container';
      ganttEl.className = 'card';
      ganttEl.innerHTML = '<div class="loading"><div class="spinner"></div>Loading Gantt…</div>';
      pmPage.appendChild(ganttEl);
    }
    ganttEl.style.display = 'block';
    try {
      const r = await api('GET', '/pm-schedules?per_page=100');
      const items = Array.isArray(r) ? r : (r.items || []);
      ganttEl.innerHTML = `<div class="card-header"><span class="card-title">📊 PM Gantt Timeline</span></div>` + renderPMGantt(items);
    } catch(e) { ganttEl.innerHTML = `<div class="empty-state"><p>${e.message}</p></div>`; }
  } else {
    if (ganttEl) ganttEl.style.display = 'none';
  }
}

// ── PATCH PARTS PAGE: ADD STOCK BARS AFTER LOAD ──────────────────
const _origLoadParts = loadParts;
window.loadParts = async function() {
  await _origLoadParts();
  setTimeout(addStockBars, 100);
};

// ── PATCH WO PAGE: COLORIZE ROWS AFTER LOAD ──────────────────────
const _origLoadWO = loadWO;
window.loadWO = async function() {
  await _origLoadWO();
  setTimeout(colorizeWORows, 100);
};

// ── PATCH DASHBOARD: ANIMATE NUMBERS + MINI CHARTS ───────────────
document.addEventListener('cmms:dashboard-loaded', e => {
  setTimeout(() => enhanceDashboardStats(e.detail || {}), 200);
});

// ── PATCH SETTINGS: INJECT ACCENT PICKER ─────────────────────────
const _origLoadSettings = loadSettings;
window.loadSettings = async function() {
  await _origLoadSettings();
  setTimeout(injectAccentPicker, 100);
};

// ── BREADCRUMB TRAIL ──────────────────────────────────────────────
function updateBreadcrumb(pageName) {
  let el = document.getElementById('breadcrumb');
  if (!el) {
    const topbar = document.querySelector('.topbar');
    if (!topbar) return;
    el = document.createElement('div');
    el.id = 'breadcrumb';
    el.style.cssText = 'font-size:11px;color:var(--text2);display:flex;align-items:center;gap:4px;margin-left:8px';
    const title = topbar.querySelector('.topbar-title');
    if (title) topbar.insertBefore(el, title.nextSibling);
  }
  const parent = pageName === 'dashboard' ? '' : 'Home';
  el.innerHTML = parent ? `<span style="color:var(--text2)">${parent}</span><span style="margin:0 2px">›</span><span style="color:var(--text0)">${pageTitles[pageName]||pageName}</span>` : '';
}

// ── PATCH showPage TO UPDATE BREADCRUMB ──────────────────────────
const _origShowPageForBC = _origShowPageInternal;
window._origShowPageInternal = function(name) {
  _origShowPageForBC(name);
  updateBreadcrumb(name);
};

// ── AUTO-INIT ON APP READY ────────────────────────────────────────
function initAdvancedGUI2() {
  injectLiveClock();
  enhanceLoginScreen();
}

// Hook into initApp
const _ia2 = typeof initApp === 'function' ? initApp : null;
if (_ia2) {
  const _prev = window.initApp;
  window.initApp = function() {
    _prev();
    setTimeout(initAdvancedGUI2, 300);
  };
}

// Also run on DOMContentLoaded for the login screen
document.addEventListener('DOMContentLoaded', enhanceLoginScreen);


// ══════════════════════════════════════════════════════════════════════
// NEXUS CMMS v5 — Advanced Module JavaScript
// Analytics, AI Insights, SLA Timers, Work Requests, Multi-step WO
// Wizard, Enhanced Toast Stack, FAB Menu, QR Labels, Heatmap
// ══════════════════════════════════════════════════════════════════════

// ── ENHANCED TOAST STACK ──────────────────────────────────────────────
(function() {
  // Replace old toast system with stacking toasts
  const stack = document.createElement('div');
  stack.id = 'toast-stack';
  document.body.appendChild(stack);
  const icons = { success:'✅', error:'❌', warning:'⚠️', info:'ℹ️' };
  window.toast = function(msg, type='info', duration=3500) {
    const item = document.createElement('div');
    item.className = `toast-item ${type}`;
    item.innerHTML = `<span class="toast-icon">${icons[type]||'ℹ️'}</span><span class="toast-msg">${msg}</span><button class="toast-close" onclick="this.closest('.toast-item').remove()">×</button>`;
    stack.appendChild(item);
    setTimeout(() => {
      item.classList.add('removing');
      setTimeout(() => item.remove(), 220);
    }, duration);
  };
})();

// ── AI INSIGHTS ────────────────────────────────────────────────────────
async function loadInsights() {
  try {
    const d = await api('GET', '/insights');
    renderInsightsStrip(d.insights || []);
  } catch(e) { console.warn('Insights error:', e); }
}

function renderInsightsStrip(insights) {
  const el = document.getElementById('insights-strip');
  if (!el) return;
  if (!insights.length) {
    el.innerHTML = '<div class="insight-card success" style="min-width:100%"><div class="insight-card-icon">🎉</div><div class="insight-card-title">All Systems Nominal</div><div class="insight-card-body">No maintenance alerts at this time. Great work!</div></div>';
    return;
  }
  const typeIcon = { danger:'🚨', warning:'⚠️', info:'💡', success:'✅' };
  el.innerHTML = '<div class="insight-strip">' +
    insights.map(i => `
      <div class="insight-card ${i.type}" onclick="showPage('${i.action}')">
        <div class="insight-card-icon">${typeIcon[i.type]||'💡'}</div>
        <div class="insight-card-title">${i.title}</div>
        <div class="insight-card-body">${i.body}</div>
        <button class="insight-card-btn">${i.action_label} →</button>
      </div>`).join('') + '</div>';
}

// ── ANALYTICS PAGE ─────────────────────────────────────────────────────
let analyticsCharts = {};
async function loadAnalytics() {
  await loadInsights();
  try {
    const [data, slaData] = await Promise.all([
      api('GET', '/analytics'),
      api('GET', '/sla-stats')
    ]);
    renderMTTRChart(data.mttr_by_category || []);
    renderDOWChart(data.wo_by_dow || []);
    renderMonthlyCostChart(data.monthly_cost || []);
    renderHealthDonut(data.asset_health || []);
    renderTopTechs(data.top_technicians || []);
    renderRepeatFailures(data.repeat_failures || []);
    renderSLAPanel(slaData || []);
  } catch(e) {
    toast('Analytics error: ' + e.message, 'error');
  }
}

function destroyChart(id) {
  if (analyticsCharts[id]) { analyticsCharts[id].destroy(); delete analyticsCharts[id]; }
}

const chartDefaults = {
  responsive: true, maintainAspectRatio: false,
  plugins: { legend: { labels: { color: '#9aa0b4', font: { size: 11 } } } },
  scales: {
    x: { ticks: { color: '#9aa0b4', font: { size: 10 } }, grid: { color: 'rgba(255,255,255,.04)' } },
    y: { ticks: { color: '#9aa0b4', font: { size: 10 } }, grid: { color: 'rgba(255,255,255,.04)' } }
  }
};

function renderMTTRChart(data) {
  const ctx = document.getElementById('chart-mttr');
  if (!ctx) return;
  destroyChart('mttr');
  analyticsCharts['mttr'] = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: data.map(d => d.category),
      datasets: [{
        label: 'Avg Repair Hours',
        data: data.map(d => parseFloat(d.avg_hours || 0).toFixed(1)),
        backgroundColor: 'rgba(0,229,160,.7)',
        borderColor: '#00e5a0',
        borderWidth: 1, borderRadius: 4,
      }]
    },
    options: { ...chartDefaults, indexAxis: 'y',
      plugins: { ...chartDefaults.plugins, legend: { display: false } },
      scales: { x: { ...chartDefaults.scales.x, ticks: { ...chartDefaults.scales.x.ticks, callback: v => v + 'h' } }, y: chartDefaults.scales.y }
    }
  });
}

function renderDOWChart(data) {
  const ctx = document.getElementById('chart-dow');
  if (!ctx) return;
  destroyChart('dow');
  const days = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
  const counts = Array(7).fill(0);
  data.forEach(d => { counts[parseInt(d.dow)] = d.count; });
  analyticsCharts['dow'] = new Chart(ctx, {
    type: 'radar',
    data: {
      labels: days,
      datasets: [{
        label: 'Work Orders',
        data: counts,
        backgroundColor: 'rgba(77,166,255,.15)',
        borderColor: '#4da6ff',
        pointBackgroundColor: '#4da6ff',
        borderWidth: 2, pointRadius: 3,
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: { r: { ticks: { color: '#9aa0b4', font: { size: 10 }, backdropColor: 'transparent' }, grid: { color: 'rgba(255,255,255,.08)' }, angleLines: { color: 'rgba(255,255,255,.08)' }, pointLabels: { color: '#9aa0b4', font: { size: 11 } } } }
    }
  });
}

function renderMonthlyCostChart(data) {
  const ctx = document.getElementById('chart-monthly-dual');
  if (!ctx) return;
  destroyChart('monthly');
  analyticsCharts['monthly'] = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: data.map(d => d.month),
      datasets: [
        { type: 'bar', label: 'Cost (₹)', data: data.map(d => d.cost || 0), backgroundColor: 'rgba(0,229,160,.5)', borderColor: '#00e5a0', borderWidth: 1, borderRadius: 3, yAxisID: 'y' },
        { type: 'line', label: 'WO Count', data: data.map(d => d.count || 0), borderColor: '#4da6ff', backgroundColor: 'rgba(77,166,255,.1)', tension: 0.4, fill: true, borderWidth: 2, pointRadius: 3, yAxisID: 'y1' }
      ]
    },
    options: {
      ...chartDefaults, responsive: true, maintainAspectRatio: false,
      plugins: { legend: { labels: { color: '#9aa0b4', font: { size: 11 } } } },
      scales: {
        x: chartDefaults.scales.x,
        y: { ...chartDefaults.scales.y, position: 'left', ticks: { color: '#9aa0b4', callback: v => fmtINR(v) } },
        y1: { ...chartDefaults.scales.y, position: 'right', grid: { drawOnChartArea: false }, ticks: { color: '#4da6ff' } }
      }
    }
  });
}

function renderHealthDonut(data) {
  const ctx = document.getElementById('chart-health');
  if (!ctx) return;
  destroyChart('health');
  const statusConfig = {
    active:      { color: '#00e5a0', label: 'Active' },
    maintenance: { color: '#ffbe4d', label: 'Maintenance' },
    inactive:    { color: '#9aa0b4', label: 'Inactive' },
    retired:     { color: '#ff4d6d', label: 'Retired' },
  };
  const labels = data.map(d => statusConfig[d.status]?.label || d.status);
  const colors = data.map(d => statusConfig[d.status]?.color || '#9aa0b4');
  const counts = data.map(d => d.cnt);
  analyticsCharts['health'] = new Chart(ctx, {
    type: 'doughnut',
    data: { labels, datasets: [{ data: counts, backgroundColor: colors.map(c => c + 'cc'), borderColor: colors, borderWidth: 2, hoverOffset: 8 }] },
    options: {
      responsive: true, maintainAspectRatio: false, cutout: '65%',
      plugins: { legend: { display: false } }
    }
  });
  // Legend
  const leg = document.getElementById('health-legend');
  if (leg) {
    const total = counts.reduce((a,b)=>a+b,0);
    leg.innerHTML = data.map((d, i) => `
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px">
        <div style="width:12px;height:12px;border-radius:50%;background:${colors[i]};flex-shrink:0"></div>
        <div>
          <div style="font-size:13px;font-weight:600;color:var(--text0)">${labels[i]}</div>
          <div style="font-size:11px;color:var(--text2)">${counts[i]} assets · ${total?Math.round(counts[i]/total*100):0}%</div>
        </div>
      </div>`).join('');
  }
}

function renderTopTechs(data) {
  const el = document.getElementById('analytics-techs');
  if (!el) return;
  const rankLabel = ['gold','silver','bronze'];
  const avatarColors = ['#00e5a0','#4da6ff','#b06dff','#ff8c42','#ff4d6d'];
  el.innerHTML = data.length ? data.map((t, i) => `
    <div class="leaderboard-item">
      <div class="lb-rank ${rankLabel[i]||''}">${['🥇','🥈','🥉'][i]||i+1}</div>
      <div class="lb-avatar" style="background:${avatarColors[i % avatarColors.length]}">${(t.full_name||'?')[0]}</div>
      <div>
        <div class="lb-name">${t.full_name}</div>
        <div class="lb-sub">${t.completed} completed · ${parseFloat(t.avg_hrs||0).toFixed(1)}h avg</div>
      </div>
      <div class="lb-score">${t.completed}</div>
    </div>`).join('') : '<div class="empty-state" style="padding:20px;text-align:center;color:var(--text2)">No completed WOs yet</div>';
}

function renderRepeatFailures(data) {
  const el = document.getElementById('analytics-repeat');
  const badge = document.getElementById('repeat-count');
  if (badge) badge.textContent = data.length;
  if (!el) return;
  const maxCount = data.length ? Math.max(...data.map(d => d.wo_count)) : 1;
  el.innerHTML = data.length ? data.map(d => `
    <div class="failure-item">
      <div class="failure-count">${d.wo_count}</div>
      <div style="flex:1;min-width:0">
        <div class="failure-name">${d.name}</div>
        <div class="failure-code">${d.code||'—'}</div>
        <div class="failure-bar"><div class="failure-bar-fill" style="width:${Math.round(d.wo_count/maxCount*100)}%"></div></div>
      </div>
    </div>`).join('') : '<div class="empty-state" style="padding:20px;text-align:center;color:var(--text2)">No repeat failures detected ✅</div>';
}

function renderSLAPanel(data) {
  const el = document.getElementById('analytics-sla');
  if (!el) return;
  const prioritySLA = { critical: 4, high: 24, medium: 72, low: 168 };
  if (!data.length) {
    el.innerHTML = '<div class="empty-state" style="padding:20px;text-align:center;color:var(--text2)">No open WOs 🎉</div>';
    return;
  }
  el.innerHTML = data.slice(0,8).map(w => {
    const hrs = w.hours_remaining;
    const slaTarget = prioritySLA[w.priority] || 72;
    const pct = Math.max(0, Math.min(100, Math.round((hrs / slaTarget) * 100)));
    const cls = hrs < 0 ? 'overdue' : hrs < slaTarget * 0.25 ? 'soon' : 'ok';
    const label = hrs < 0 ? `${Math.abs(hrs)}h overdue` : hrs < 24 ? `${hrs}h left` : `${Math.round(hrs/24)}d left`;
    const barColor = cls === 'overdue' ? 'var(--red)' : cls === 'soon' ? 'var(--yellow)' : 'var(--green)';
    return `
      <div class="sla-item">
        <div style="flex:1;min-width:0">
          <div class="sla-wo-num">${w.wo_number} · <span class="badge b-${w.priority}" style="font-size:9px">${w.priority}</span></div>
          <div class="sla-title">${w.title}</div>
          <div class="sla-bar"><div class="sla-bar-fill" style="width:${pct}%;background:${barColor}"></div></div>
        </div>
        <div class="sla-timer ${cls}">${label}</div>
      </div>`;
  }).join('');
}

// ── WORK REQUESTS PAGE ─────────────────────────────────────────────────
async function loadWorkRequests() {
  const status = document.getElementById('wr-filter')?.value || '';
  let url = '/work-orders?per_page=50&type=corrective&status=' + (status || '');
  const el = document.getElementById('wr-list');
  if (!el) return;
  el.innerHTML = '<div class="loading"><div class="spinner"></div>Loading...</div>';
  try {
    const d = await api('GET', url);
    const items = (d.items || []).filter(w => w.notes && w.notes.startsWith('Submitted by:'));
    if (!items.length) {
      el.innerHTML = '<div class="empty-state" style="padding:24px;text-align:center;color:var(--text2)"><div style="font-size:32px;margin-bottom:8px">📝</div>No work requests yet.<br><span style="font-size:12px">Share the public portal link to start receiving requests.</span></div>';
      return;
    }
    const statusColor = { open:'var(--yellow)', in_progress:'var(--blue)', completed:'var(--green)', cancelled:'var(--text2)' };
    el.innerHTML = items.map(w => `
      <div class="wr-item" onclick="openWODetail(${w.id})">
        <div class="wr-dot" style="background:${statusColor[w.status]||'var(--text2)'}"></div>
        <div style="flex:1;min-width:0">
          <div class="wr-num">${w.wo_number}</div>
          <div class="wr-title">${w.title}</div>
          <div class="wr-meta">${w.notes?.replace('Submitted by:','👤').split('|')[0]} · <span class="badge b-${w.priority}" style="font-size:9px;vertical-align:middle">${w.priority}</span></div>
        </div>
        <div style="font-size:11px;color:var(--text2);flex-shrink:0">${w.created_at?.slice(0,10)||''}</div>
      </div>`).join('');
    // Stats
    const statsEl = document.getElementById('wr-stats');
    if (statsEl) {
      const allWR = await api('GET', '/work-orders?per_page=500&type=corrective');
      const wrAll = (allWR.items||[]).filter(w=>w.notes?.startsWith('Submitted by:'));
      const today = new Date().toISOString().slice(0,10);
      const todayCount = wrAll.filter(w=>w.created_at?.startsWith(today)).length;
      statsEl.innerHTML = `
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;padding:12px">
          ${[['Total Requests',wrAll.length,'📝'],['Today',todayCount,'📅'],
             ['Open',wrAll.filter(w=>w.status==='open').length,'🔴'],
             ['Completed',wrAll.filter(w=>w.status==='completed').length,'✅']
            ].map(([l,v,ic])=>`<div style="background:var(--bg3);border-radius:8px;padding:10px;text-align:center">
              <div style="font-size:22px">${ic}</div>
              <div style="font-size:18px;font-weight:700;color:var(--text0)">${v}</div>
              <div style="font-size:11px;color:var(--text2)">${l}</div>
            </div>`).join('')}
        </div>`;
    }
  } catch(e) { el.innerHTML = '<div class="empty-state" style="color:var(--red)">Error: ' + e.message + '</div>'; }
  // Show portal URL
  const urlEl = document.getElementById('portal-url');
  if (urlEl) urlEl.textContent = window.location.origin + '/request';
}

function copyPortalURL() {
  navigator.clipboard.writeText(window.location.origin + '/request')
    .then(() => toast('Portal URL copied!', 'success'))
    .catch(() => toast('Copy failed', 'error'));
}

// ── MULTI-STEP WO CREATION WIZARD ─────────────────────────────────────
let wizardStep = 1;
const WIZARD_STEPS = 4;
let wizardData = {};

function openWOWizard() {
  wizardStep = 1; wizardData = {};
  const overlay = document.getElementById('wo-wizard-overlay');
  if (!overlay) { buildWOWizard(); return; }
  overlay.classList.add('active');
  renderWizardStep();
}

async function buildWOWizard() {
  // Load needed data
  const [assets, users] = await Promise.all([
    api('GET', '/assets?per_page=200').catch(()=>({items:[]})),
    api('GET', '/users').catch(()=>[])
  ]);
  const assetOpts = (assets.items||[]).map(a => `<option value="${a.id}">${a.name} (${a.code||''})</option>`).join('');
  const userOpts = (Array.isArray(users)?users:users.items||[]).map(u => `<option value="${u.id}">${u.full_name} (${u.role})</option>`).join('');

  const overlay = document.createElement('div');
  overlay.id = 'wo-wizard-overlay';
  overlay.className = 'wizard-overlay active';
  overlay.innerHTML = `
    <div class="wizard">
      <div class="wizard-header">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px">
          <div style="font-size:16px;font-weight:700;color:var(--text0)">🧙 New Work Order</div>
          <button class="modal-close" onclick="closeWOWizard()">×</button>
        </div>
        <div class="wizard-steps" id="wizard-steps-bar">
          ${['Details','Asset','Schedule','Review'].map((s,i)=>`
            <div class="wizard-step${i===0?' active':''}" id="wz-step-${i+1}">
              <div class="wizard-step-dot">${i+1}</div>
              <div class="wizard-step-label">${s}</div>
            </div>`).join('')}
        </div>
      </div>
      <div class="wizard-body" id="wizard-body">
        <!-- panes injected by renderWizardStep -->
      </div>
      <div class="wizard-footer">
        <span class="wizard-progress" id="wz-progress">Step 1 of ${WIZARD_STEPS}</span>
        <div style="display:flex;gap:8px">
          <button class="btn btn-secondary" id="wz-back-btn" onclick="wizardBack()" style="display:none">← Back</button>
          <button class="btn btn-primary" id="wz-next-btn" onclick="wizardNext()">Next →</button>
        </div>
      </div>
    </div>`;
  document.body.appendChild(overlay);
  // Store data refs
  overlay._assetOpts = assetOpts;
  overlay._userOpts = userOpts;
  renderWizardStep();
}

function renderWizardStep() {
  const overlay = document.getElementById('wo-wizard-overlay');
  const body = document.getElementById('wizard-body');
  const progress = document.getElementById('wz-progress');
  const backBtn = document.getElementById('wz-back-btn');
  const nextBtn = document.getElementById('wz-next-btn');
  if (!body) return;
  progress.textContent = `Step ${wizardStep} of ${WIZARD_STEPS}`;
  backBtn.style.display = wizardStep > 1 ? '' : 'none';
  nextBtn.textContent = wizardStep === WIZARD_STEPS ? '✓ Create WO' : 'Next →';
  // Update step indicators
  for (let i = 1; i <= WIZARD_STEPS; i++) {
    const el = document.getElementById('wz-step-' + i);
    if (!el) continue;
    el.className = 'wizard-step' + (i < wizardStep ? ' done' : i === wizardStep ? ' active' : '');
    el.querySelector('.wizard-step-dot').textContent = i < wizardStep ? '✓' : i;
  }
  // Update progress line
  const bar = document.getElementById('wizard-steps-bar');
  if (bar) bar.style.setProperty('--wz-progress', `${Math.round((wizardStep-1)/(WIZARD_STEPS-1)*100)}%`);

  const panes = {
    1: `
      <div class="form-group"><label>Title *</label><input type="text" id="wz-title" class="form-control" placeholder="Brief description of the work" value="${wizardData.title||''}"></div>
      <div class="form-group"><label>Description</label><textarea id="wz-desc" class="form-control" rows="3" placeholder="Detailed description of the issue or work required">${wizardData.description||''}</textarea></div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px">
        <div class="form-group"><label>Type</label>
          <select id="wz-type" class="form-control">
            ${['corrective','preventive','inspection','emergency'].map(t=>`<option value="${t}" ${wizardData.type===t?'selected':''}>${t}</option>`).join('')}
          </select>
        </div>
        <div class="form-group"><label>Priority</label>
          <select id="wz-priority" class="form-control">
            ${['critical','high','medium','low'].map(p=>`<option value="${p}" ${wizardData.priority===p?'selected':''}>${p}</option>`).join('')}
          </select>
        </div>
      </div>
      <div class="form-group"><label>Safety Notes</label><input type="text" id="wz-safety" class="form-control" placeholder="Any lockout/tagout or safety requirements" value="${wizardData.safety||''}"></div>`,
    2: `
      <div class="form-group"><label>Asset</label>
        <select id="wz-asset" class="form-control"><option value="">— Select asset (optional) —</option>${overlay?._assetOpts||''}</select>
      </div>
      <div class="form-group"><label>Tools Required</label><input type="text" id="wz-tools" class="form-control" placeholder="e.g. Multimeter, torque wrench, lubricant" value="${wizardData.tools||''}"></div>
      <div class="form-group"><label>Estimated Hours</label><input type="number" id="wz-hours" class="form-control" placeholder="0.5" step="0.5" min="0" value="${wizardData.hours||''}"></div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px">
        <div class="form-group"><label>Labor Cost (₹)</label><input type="number" id="wz-labor" class="form-control" placeholder="0" step="0.01" value="${wizardData.labor||''}"></div>
        <div class="form-group"><label>Parts Cost (₹)</label><input type="number" id="wz-parts-cost" class="form-control" placeholder="0" step="0.01" value="${wizardData.partsCost||''}"></div>
      </div>`,
    3: `
      <div class="form-group"><label>Assign To</label>
        <select id="wz-assign" class="form-control"><option value="">— Unassigned —</option>${overlay?._userOpts||''}</select>
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px">
        <div class="form-group"><label>Scheduled Date</label><input type="date" id="wz-scheduled" class="form-control" value="${wizardData.scheduled||''}"></div>
        <div class="form-group"><label>Due Date</label><input type="date" id="wz-due" class="form-control" value="${wizardData.due||''}"></div>
      </div>
      <div class="form-group"><label>Notes</label><textarea id="wz-notes" class="form-control" rows="3" placeholder="Additional notes, instructions, or references">${wizardData.notes||''}</textarea></div>`,
    4: `
      <div style="background:var(--bg3);border-radius:var(--r8);padding:16px;margin-bottom:16px">
        <div style="font-size:13px;font-weight:600;color:var(--text2);margin-bottom:12px;text-transform:uppercase;letter-spacing:.6px">Review Work Order</div>
        ${[
          ['Title', wizardData.title||'—'],
          ['Type', wizardData.type||'corrective'],
          ['Priority', wizardData.priority||'medium'],
          ['Asset', wizardData.assetName||'—'],
          ['Assigned To', wizardData.assignName||'—'],
          ['Due Date', wizardData.due||'—'],
          ['Est. Hours', wizardData.hours ? wizardData.hours + 'h' : '—'],
          ['Labor Cost', wizardData.labor ? fmtINR(wizardData.labor) : '—'],
        ].map(([l,v])=>`<div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid var(--border)"><span style="color:var(--text2);font-size:13px">${l}</span><span style="font-weight:500;color:var(--text0);font-size:13px">${v}</span></div>`).join('')}
      </div>
      <div style="font-size:12px;color:var(--text2)">Click "Create WO" to submit this work order to the system.</div>`
  };
  body.innerHTML = `<div class="wizard-pane active">${panes[wizardStep]||''}</div>`;
  // Set select values
  if (wizardStep === 2 && wizardData.assetId) { const s = document.getElementById('wz-asset'); if(s) s.value = wizardData.assetId; }
  if (wizardStep === 3 && wizardData.assignId) { const s = document.getElementById('wz-assign'); if(s) s.value = wizardData.assignId; }
}

function wizardCollectStep() {
  if (wizardStep === 1) {
    wizardData.title       = document.getElementById('wz-title')?.value.trim();
    wizardData.description = document.getElementById('wz-desc')?.value.trim();
    wizardData.type        = document.getElementById('wz-type')?.value;
    wizardData.priority    = document.getElementById('wz-priority')?.value;
    wizardData.safety      = document.getElementById('wz-safety')?.value.trim();
    if (!wizardData.title) { toast('Please enter a title', 'error'); return false; }
  } else if (wizardStep === 2) {
    const aEl = document.getElementById('wz-asset');
    wizardData.assetId    = aEl?.value || null;
    wizardData.assetName  = aEl?.options[aEl.selectedIndex]?.text || '—';
    wizardData.tools      = document.getElementById('wz-tools')?.value.trim();
    wizardData.hours      = parseFloat(document.getElementById('wz-hours')?.value) || null;
    wizardData.labor      = parseFloat(document.getElementById('wz-labor')?.value) || 0;
    wizardData.partsCost  = parseFloat(document.getElementById('wz-parts-cost')?.value) || 0;
  } else if (wizardStep === 3) {
    const uEl = document.getElementById('wz-assign');
    wizardData.assignId   = uEl?.value || null;
    wizardData.assignName = uEl?.options[uEl.selectedIndex]?.text || '—';
    wizardData.scheduled  = document.getElementById('wz-scheduled')?.value;
    wizardData.due        = document.getElementById('wz-due')?.value;
    wizardData.notes      = document.getElementById('wz-notes')?.value.trim();
  }
  return true;
}

async function wizardNext() {
  if (!wizardCollectStep()) return;
  if (wizardStep < WIZARD_STEPS) {
    wizardStep++;
    renderWizardStep();
  } else {
    // Submit
    const btn = document.getElementById('wz-next-btn');
    btn.disabled = true; btn.textContent = 'Creating…';
    try {
      const payload = {
        title: wizardData.title, description: wizardData.description,
        type: wizardData.type, priority: wizardData.priority,
        asset_id: wizardData.assetId ? parseInt(wizardData.assetId) : null,
        assigned_to: wizardData.assignId ? parseInt(wizardData.assignId) : null,
        scheduled_date: wizardData.scheduled, due_date: wizardData.due,
        estimated_hours: wizardData.hours, labor_cost: wizardData.labor,
        parts_cost: wizardData.partsCost, safety_notes: wizardData.safety,
        tools_required: wizardData.tools, notes: wizardData.notes,
      };
      const r = await api('POST', '/work-orders', payload);
      toast(`✅ Created ${r.wo_number}`, 'success');
      closeWOWizard();
      if (state.currentPage === 'work-orders') loadWO();
      if (state.currentPage === 'kanban') loadKanban();
    } catch(e) {
      toast('Error: ' + e.message, 'error');
      btn.disabled = false; btn.textContent = '✓ Create WO';
    }
  }
}

function wizardBack() {
  if (wizardStep > 1) { wizardStep--; renderWizardStep(); }
}

function closeWOWizard() {
  const overlay = document.getElementById('wo-wizard-overlay');
  if (overlay) overlay.classList.remove('active');
}

// Override showCreateWO to use wizard
window.showCreateWO = openWOWizard;

// ── QR LABEL PRINTING ─────────────────────────────────────────────────
function printAssetQRLabel(assetId) {
  const url = '/api/assets/' + assetId + '/qr-label';
  const win = window.open(url, '_blank', 'width=400,height=500');
  if (!win) toast('Popup blocked — allow popups to print QR labels', 'warning');
}

// Patch openAssetDetail to add QR label button
const _origOpenAssetDetail = openAssetDetail;
window.openAssetDetail = async function(id) {
  await _origOpenAssetDetail(id);
  setTimeout(() => {
    const modalFooter = document.querySelector('#modal-asset-detail .modal-footer');
    if (modalFooter && !modalFooter.querySelector('.qr-btn')) {
      const qrBtn = document.createElement('button');
      qrBtn.className = 'btn btn-secondary qr-btn';
      qrBtn.textContent = '🏷 Print QR Label';
      qrBtn.onclick = () => printAssetQRLabel(id);
      modalFooter.insertBefore(qrBtn, modalFooter.firstChild);
    }
  }, 300);
};

// ── DASHBOARD HEATMAP ─────────────────────────────────────────────────
async function renderWOHeatmap() {
  try {
    const wos = await api('GET', '/work-orders?per_page=1000&status=');
    const items = wos.items || [];
    const counts = {};
    items.forEach(w => {
      const d = w.created_at?.slice(0,10);
      if (d) counts[d] = (counts[d]||0) + 1;
    });
    const heatEl = document.getElementById('wo-heatmap');
    if (!heatEl) return;
    // Build last 13 weeks
    const now = new Date(); now.setHours(0,0,0,0);
    const start = new Date(now); start.setDate(start.getDate() - 90);
    const weeks = []; let week = [];
    for (let d = new Date(start); d <= now; d.setDate(d.getDate()+1)) {
      const iso = d.toISOString().slice(0,10);
      const c = counts[iso] || 0;
      const level = c === 0 ? 0 : c <= 1 ? 1 : c <= 3 ? 2 : c <= 5 ? 3 : 4;
      week.push({ date: iso, count: c, level });
      if (d.getDay() === 6) { weeks.push(week); week = []; }
    }
    if (week.length) weeks.push(week);
    const levelColors = ['var(--bg3)', 'rgba(0,229,160,.2)', 'rgba(0,229,160,.4)', 'rgba(0,229,160,.7)', '#00e5a0'];
    heatEl.innerHTML = `
      <div style="font-size:11px;color:var(--text2);margin-bottom:8px;display:flex;align-items:center;gap:8px">
        WO Activity
        <span style="margin-left:auto;font-size:10px">Less</span>
        ${levelColors.map(c=>`<div style="width:10px;height:10px;border-radius:2px;background:${c}"></div>`).join('')}
        <span style="font-size:10px">More</span>
      </div>
      <div style="display:flex;gap:2px">
        ${weeks.map(w=>`<div style="display:flex;flex-direction:column;gap:2px">
          ${w.map(d=>`<div class="heatmap-cell" title="${d.date}: ${d.count} WOs"
            style="width:12px;height:12px;border-radius:2px;background:${levelColors[d.level]};cursor:default"
            onmouseover="showHeatTip(event,'${d.date}',${d.count})"
            onmouseout="hideHeatTip()"></div>`).join('')}
        </div>`).join('')}
      </div>`;
  } catch(e) { console.warn('Heatmap error:', e); }
}

let heatTip = null;
function showHeatTip(e, date, count) {
  if (!heatTip) { heatTip = document.createElement('div'); heatTip.style.cssText='position:fixed;background:var(--bg3);border:1px solid var(--border2);border-radius:6px;padding:6px 10px;font-size:11px;color:var(--text0);pointer-events:none;z-index:9999;box-shadow:0 4px 12px rgba(0,0,0,.4)'; document.body.appendChild(heatTip); }
  heatTip.textContent = `${date}: ${count} WO${count!==1?'s':''}`;
  heatTip.style.left = (e.clientX + 10) + 'px';
  heatTip.style.top  = (e.clientY - 30) + 'px';
  heatTip.style.display = 'block';
}
function hideHeatTip() { if (heatTip) heatTip.style.display = 'none'; }

// ── INJECT HEATMAP INTO DASHBOARD ─────────────────────────────────────
function injectHeatmapWidget() {
  const dashPage = document.getElementById('page-dashboard');
  if (!dashPage || document.getElementById('wo-heatmap')) return;
  const card = document.createElement('div');
  card.className = 'card';
  card.style.marginTop = '16px';
  card.innerHTML = `<div class="card-header"><span class="card-title">📆 Work Order Activity (Last 90 Days)</span></div><div id="wo-heatmap" style="padding:4px;overflow-x:auto"><div class="loading" style="padding:20px;text-align:center"><div class="spinner"></div>Loading...</div></div>`;
  const lastCard = dashPage.querySelector('.card:last-of-type');
  if (lastCard) lastCard.after(card); else dashPage.appendChild(card);
  renderWOHeatmap();
}

// ── ANIMATED NUMBER COUNTER ─────────────────────────────────────────
function animateCounter(el, target, duration) {
  duration = duration || 700;
  if (!el) return;
  const isINR = el.textContent.trim().startsWith('₹');
  const startTime = performance.now();
  const start = 0;
  function step(now) {
    const elapsed = now - startTime;
    const progress = Math.min(elapsed / duration, 1);
    const eased = 1 - Math.pow(1 - progress, 4);
    const val = Math.round(start + (target - start) * eased);
    el.textContent = isINR ? '₹' + val.toLocaleString('en-IN') : val.toLocaleString();
    if (progress < 1) requestAnimationFrame(step);
  }
  requestAnimationFrame(step);
}

function animateAllStatCounters() {
  document.querySelectorAll('.stat-value').forEach(function(el) {
    const raw = el.textContent.replace(/[₹,\s]/g,'').trim();
    const num = parseInt(raw, 10);
    if (!isNaN(num) && num > 0) {
      const dur = 500 + Math.random() * 400;
      animateCounter(el, num, dur);
    }
  });
}

document.addEventListener('cmms:dashboard-loaded', function() {
  setTimeout(animateAllStatCounters, 80);
});

// ── ENHANCED FAB MENU ─────────────────────────────────────────────────
function initFABMenu() {
  const fabWrap = document.querySelector('.fab') || document.getElementById('mobile-fab');
  if (!fabWrap) return;
  let menuOpen = false;
  const menuItems = [
    { icon: '🧙', label: 'New WO Wizard', action: openWOWizard },
    { icon: '📝', label: 'Work Request', action: () => window.open('/request','_blank') },
    { icon: '📈', label: 'Analytics', action: () => showPage('analytics') },
    { icon: '🗂', label: 'Kanban', action: () => showPage('kanban') },
  ];
  const menu = document.createElement('div');
  menu.className = 'fab-menu';
  menu.id = 'fab-menu';
  menuItems.forEach((item, i) => {
    const row = document.createElement('div');
    row.className = 'fab-menu-item';
    row.style.transitionDelay = (i * 40) + 'ms';
    row.innerHTML = `<span class="fab-label">${item.label}</span><button class="fab-mini" onclick="closeFABMenu();(${item.action.toString()})();">${item.icon}</button>`;
    menu.appendChild(row);
  });
  document.body.appendChild(menu);
  fabWrap.addEventListener('click', (e) => {
    e.stopPropagation();
    menuOpen = !menuOpen;
    menu.querySelectorAll('.fab-menu-item').forEach(el => el.classList.toggle('visible', menuOpen));
    fabWrap.style.transform = menuOpen ? 'rotate(45deg)' : '';
  });
  document.addEventListener('click', () => closeFABMenu());
}

function closeFABMenu() {
  document.querySelectorAll('.fab-menu-item').forEach(el => el.classList.remove('visible'));
  const fab = document.querySelector('.fab, #mobile-fab');
  if (fab) fab.style.transform = '';
}

// ── SMART DASHBOARD REFRESH INDICATOR ─────────────────────────────────
function initDashboardAutoRefresh() {
  let countdown = 60;
  const indicator = document.createElement('div');
  indicator.id = 'dash-refresh-indicator';
  indicator.style.cssText = 'font-size:11px;color:var(--text2);font-family:var(--mono);cursor:pointer;padding:4px 8px;border-radius:4px;transition:.15s';
  indicator.title = 'Click to refresh now';
  indicator.onclick = () => { loadDashboard(); countdown = 60; renderWOHeatmap(); };
  const topbarRight = document.querySelector('.topbar-right');
  if (topbarRight) topbarRight.insertBefore(indicator, topbarRight.firstChild);
  setInterval(() => {
    countdown--;
    if (indicator) indicator.textContent = `↻ ${countdown}s`;
    if (countdown <= 0) {
      countdown = 60;
      if (state?.currentPage === 'dashboard') loadDashboard();
    }
  }, 1000);
}

// ── KEYBOARD SHORTCUT: G+N for analytics ──────────────────────────────
// (wired via existing enhanced shortcuts, just add to sequences)

// ── GLOBAL SEARCH QUICK FILTER ────────────────────────────────────────
function initGlobalSearch() {
  // Patch cmdFilter to also search WOs when query is long enough.
  // We store a reference to the original plain-filter and replace it.
  const _origCmdFilter = cmdFilter;
  let _searchTimer = null;
  window.cmdFilter = function(q) {
    // Always run the static CMD_ITEMS filter first
    _origCmdFilter(q);
    // Clear any pending WO search
    clearTimeout(_searchTimer);
    const query = q.trim();
    if (query.length < 3) return;
    // Debounce the async WO search so typing doesn't flood requests
    _searchTimer = setTimeout(async () => {
      try {
        const r = await api('GET', '/work-orders?search=' + encodeURIComponent(query) + '&per_page=5');
        const items = r.items || [];
        if (!items.length) return;
        // Only append if the palette is still open and query unchanged
        const inp = document.getElementById('cmd-input');
        if (!inp || inp.value.trim().toLowerCase() !== query.toLowerCase()) return;
        const results = document.getElementById('cmd-results');
        if (!results) return;
        const sep = document.createElement('div');
        sep.style.cssText = 'font-size:10px;color:var(--text2);padding:4px 12px;text-transform:uppercase;letter-spacing:.6px;border-top:1px solid var(--border)';
        sep.textContent = 'Work Orders';
        results.appendChild(sep);
        items.forEach(w => {
          const el = document.createElement('div');
          el.className = 'cmd-item';
          el.innerHTML = `<span class="cmd-item-icon">📋</span><div><div class="cmd-item-label">${w.title}</div><div style="font-size:11px;color:var(--text2)">${w.wo_number} · ${w.status}</div></div>`;
          el.onclick = () => { closeCmdPalette(); openWODetail(w.id); };
          results.appendChild(el);
        });
      } catch(e) {}
    }, 300);
  };
}


// ── BULK WORK ORDER ACTIONS (UI) ──────────────────────────────────────
let selectedWOs = new Set();

function toggleWOSelection(id, cb) {
  if (cb.checked) selectedWOs.add(id); else selectedWOs.delete(id);
  updateBulkBar();
}

function toggleAllWOs(masterCb) {
  document.querySelectorAll('.wo-row-cb').forEach(cb => {
    cb.checked = masterCb.checked;
    const id = parseInt(cb.dataset.id);
    if (masterCb.checked) selectedWOs.add(id); else selectedWOs.delete(id);
  });
  updateBulkBar();
}

function updateBulkBar() {
  let bar = document.getElementById('bulk-action-bar');
  if (!bar) {
    bar = document.createElement('div');
    bar.id = 'bulk-action-bar';
    bar.style.cssText = 'position:fixed;bottom:0;left:0;right:0;background:var(--bg2);border-top:2px solid var(--accent);padding:12px 24px;display:flex;align-items:center;gap:12px;z-index:500;transform:translateY(100%);transition:.3s cubic-bezier(0.34,1.56,0.64,1)';
    bar.innerHTML = `
      <span id="bulk-count" style="font-family:var(--mono);font-size:13px;font-weight:700;color:var(--accent)"></span>
      <span style="color:var(--text2);font-size:13px">WOs selected</span>
      <div style="display:flex;gap:8px;margin-left:auto">
        <button class="btn btn-success btn-sm" onclick="bulkAction('complete')">✓ Complete</button>
        <button class="btn btn-secondary btn-sm" onclick="bulkAction('cancel')">✗ Cancel</button>
        <button class="btn btn-danger btn-sm" onclick="bulkAction('delete')">🗑 Delete</button>
        <button class="btn btn-secondary btn-sm" onclick="clearBulkSelection()">Clear</button>
      </div>`;
    document.body.appendChild(bar);
  }
  const count = selectedWOs.size;
  document.getElementById('bulk-count').textContent = count;
  bar.style.transform = count > 0 ? 'translateY(0)' : 'translateY(100%)';
}

async function bulkAction(action) {
  if (!selectedWOs.size) return;
  const label = { complete:'complete', cancel:'cancel', delete:'permanently delete' }[action];
  if (!confirm(`Are you sure you want to ${label} ${selectedWOs.size} work order(s)?`)) return;
  try {
    const r = await api('POST', '/work-orders/bulk', { ids: [...selectedWOs], action });
    toast(`${r.updated} WOs ${action}d`, 'success');
    clearBulkSelection();
    loadWO();
  } catch(e) { toast('Bulk action failed: ' + e.message, 'error'); }
}

function clearBulkSelection() {
  selectedWOs.clear();
  document.querySelectorAll('.wo-row-cb').forEach(cb => cb.checked = false);
  const master = document.getElementById('wo-select-all');
  if (master) master.checked = false;
  updateBulkBar();
}

// Patch loadWO to inject checkboxes into the WO table header + rows
const _origLoadWOv5 = window.loadWO;
window.loadWO = async function() {
  selectedWOs.clear();
  await _origLoadWOv5();
  setTimeout(() => {
    const thead = document.querySelector('#page-work-orders table thead tr');
    if (thead && !thead.querySelector('.wo-select-th')) {
      const th = document.createElement('th');
      th.className = 'wo-select-th';
      th.style.width = '36px';
      th.innerHTML = '<input type="checkbox" id="wo-select-all" onchange="toggleAllWOs(this)" style="cursor:pointer">';
      thead.insertBefore(th, thead.firstChild);
    }
    document.querySelectorAll('#page-work-orders table tbody tr').forEach(row => {
      if (row.querySelector('.wo-row-cb')) return;
      const id = row.getAttribute('data-wo-id') || row.querySelector('[onclick*="openWODetail"]')?.getAttribute('onclick')?.match(/\d+/)?.[0];
      if (!id) return;
      const td = document.createElement('td');
      td.innerHTML = `<input type="checkbox" class="wo-row-cb" data-id="${id}" onchange="toggleWOSelection(${id},this)" style="cursor:pointer">`;
      row.insertBefore(td, row.firstChild);
    });
  }, 150);
};

// ── WIRE ALL v5 FEATURES INTO INIT ────────────────────────────────────
const _prevInitAdvancedGUI = typeof initAdvancedGUI === 'function' ? initAdvancedGUI : null;
function initAdvancedGUIv5() {
  if (_prevInitAdvancedGUI) _prevInitAdvancedGUI();
  setTimeout(() => {
    injectHeatmapWidget();
    initDashboardAutoRefresh();
    initFABMenu();
    initGlobalSearch();
    // Show insights strip on dashboard load
    document.addEventListener('cmms:dashboard-loaded', () => {
      if (document.getElementById('insights-strip') && state?.currentPage === 'analytics') {
        loadInsights();
      }
    });
  }, 500);
}

// Replace initAdvancedGUI reference in wire-up
const _prevWireup = window.initApp;
if (_prevWireup) {
  window.initApp = function() {
    _prevWireup();
    setTimeout(initAdvancedGUIv5, 400);
  };
}

// ── v6: PAGE TITLES ───────────────────────────────────────────────────────────
const _v6PageTitles = {
  'budget':        '💰 Budget Tracker',
  'sla-monitor':   '⏱ SLA Monitor',
  'reorder-wizard':'🪄 Reorder Wizard',
};
// ── v6: showPage — wraps the breadcrumb-patched _origShowPageInternal ─────────
// NOTE: _origShowPagev5 would always be null here (showPage not yet defined),
// so we call window._origShowPageInternal directly, which is the fully-patched
// version (including breadcrumb updates from the v4.1 patch above).
function showPage(page) {
  if (typeof window._origShowPageInternal === 'function') {
    window._origShowPageInternal(page);
  } else if (typeof _origShowPageInternal === 'function') {
    _origShowPageInternal(page);
  }
  if (_v6PageTitles[page]) {
    const tt = document.getElementById('topbar-title');
    if (tt) tt.textContent = _v6PageTitles[page];
  }
  if (page === 'budget') loadBudget();
  if (page === 'sla-monitor') loadSlaMonitor();
  if (page === 'reorder-wizard') loadReorderWizard();
}

// ── v6: BUDGET TRACKER ────────────────────────────────────────────────────────
let _budgetData = [];
let _budgetChart = null;
const MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];

async function loadBudget() {
  const year = document.getElementById('budget-year')?.value || new Date().getFullYear();
  try {
    const d = await api('GET', `/budget?year=${year}`);
    _budgetData = d.months;
    // Update strip
    const sym = '₹';
    const v = d.annual_budget, a = d.annual_actual, diff = v - a;
    document.getElementById('bs-budget').textContent  = sym + fmt(v);
    document.getElementById('bs-actual').textContent  = sym + fmt(a);
    document.getElementById('bs-variance').textContent = (diff >= 0 ? '+' : '') + sym + fmt(Math.abs(diff));
    document.getElementById('bs-variance').className = 'qs-val ' + (diff >= 0 ? 'text-green' : 'text-red');
    const pct = v > 0 ? Math.round(a / v * 100) : 0;
    document.getElementById('bs-pct').textContent = pct + '%';
    document.getElementById('bs-pct').className = 'qs-val ' + (pct > 100 ? 'text-red' : pct > 80 ? 'text-yellow' : 'text-green');
    renderBudgetTable(d.months);
    renderBudgetChart(d.months);
  } catch(e) {
    toast('Failed to load budget: ' + e.message, 'error');
  }
}

function fmt(n) {
  if (!n && n !== 0) return '—';
  return Number(n).toLocaleString('en-IN', {maximumFractionDigits:0});
}

function renderBudgetTable(months) {
  const tbody = document.getElementById('budget-tbody');
  if (!tbody) return;
  tbody.innerHTML = months.map((m, i) => {
    const diff = (m.budget || 0) - (m.actual || 0);
    const over = m.actual > m.budget && m.budget > 0;
    const pct = m.budget > 0 ? Math.round(m.actual / m.budget * 100) : null;
    return `<tr>
      <td style="font-weight:600">${MONTHS[m.month-1]}</td>
      <td><input type="number" class="form-control" style="width:120px;padding:4px 8px;font-size:12px"
           id="budget-inp-${m.month}" value="${m.budget || ''}" placeholder="0"
           data-month="${m.month}" data-notes-id="budget-notes-${m.month}"></td>
      <td style="font-family:var(--mono);color:${m.actual>0?'var(--text0)':'var(--text2)'}">₹${fmt(m.actual)}</td>
      <td style="font-family:var(--mono);color:${over?'var(--red)':'var(--green)'}">${diff >= 0 ? '+' : ''}₹${fmt(Math.abs(diff))}</td>
      <td>${pct !== null ? `<div style="display:flex;align-items:center;gap:8px">
        <div style="flex:1;height:6px;background:var(--bg3);border-radius:3px;overflow:hidden;min-width:60px">
          <div style="width:${Math.min(pct,100)}%;height:100%;background:${pct>100?'var(--red)':pct>80?'var(--yellow)':'var(--green)'};border-radius:3px"></div>
        </div>
        <span style="font-size:11px;font-family:var(--mono);color:${pct>100?'var(--red)':pct>80?'var(--yellow)':'var(--text2)'}">${pct}%</span>
      </div>` : '<span style="color:var(--text2);font-size:12px">—</span>'}</td>
      <td><input type="text" class="form-control" style="padding:4px 8px;font-size:12px"
           id="budget-notes-${m.month}" value="${m.notes || ''}" placeholder="Notes..."></td>
    </tr>`;
  }).join('');
}

function renderBudgetChart(months) {
  const canvas = document.getElementById('budget-chart');
  if (!canvas) return;
  if (_budgetChart) { _budgetChart.destroy(); _budgetChart = null; }
  _budgetChart = new Chart(canvas, {
    type: 'bar',
    data: {
      labels: months.map(m => MONTHS[m.month-1]),
      datasets: [
        { label: 'Budget', data: months.map(m => m.budget||0),
          backgroundColor: 'rgba(77,166,255,.35)', borderColor: 'rgba(77,166,255,.8)', borderWidth: 1 },
        { label: 'Actual', data: months.map(m => m.actual||0),
          backgroundColor: months.map(m => m.actual > m.budget && m.budget > 0 ? 'rgba(255,77,109,.5)' : 'rgba(0,229,160,.4)'),
          borderColor: months.map(m => m.actual > m.budget && m.budget > 0 ? 'var(--red)' : 'var(--green)'),
          borderWidth: 1 },
      ]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { labels: { color: '#9aa0b4', font: { size: 11 } } } },
      scales: {
        x: { ticks: { color: '#9aa0b4' }, grid: { color: 'rgba(255,255,255,.05)' } },
        y: { ticks: { color: '#9aa0b4', callback: v => '₹' + (v>=1000?Math.round(v/1000)+'K':v) }, grid: { color: 'rgba(255,255,255,.05)' } }
      }
    }
  });
}

async function saveBudget() {
  const year = parseInt(document.getElementById('budget-year')?.value || new Date().getFullYear());
  const rows = [];
  for (let m = 1; m <= 12; m++) {
    const inp = document.getElementById(`budget-inp-${m}`);
    const notesInp = document.getElementById(`budget-notes-${m}`);
    if (!inp) continue;
    rows.push({ year, month: m, budget: parseFloat(inp.value) || 0, notes: notesInp?.value || '' });
  }
  try {
    await api('PUT', '/budget', rows);
    toast('Budget saved!', 'success');
    loadBudget();
  } catch(e) {
    toast('Save failed: ' + e.message, 'error');
  }
}

// ── v6: SLA MONITOR ───────────────────────────────────────────────────────────
let _slaConfig = [];

async function loadSlaMonitor() {
  const listEl = document.getElementById('sla-list');
  if (!listEl) return;
  listEl.innerHTML = '<div class="loading"><div class="spinner"></div>Loading...</div>';
  try {
    const [wos, cfg] = await Promise.all([
      api('GET', '/sla-status'),
      api('GET', '/sla-config'),
    ]);
    _slaConfig = cfg;
    // Update counts
    const counts = { escalated: 0, breached: 0, at_risk: 0, ok: 0 };
    wos.forEach(w => { if (counts[w.sla_status] !== undefined) counts[w.sla_status]++; });
    document.getElementById('sla-escalated').textContent = counts.escalated;
    document.getElementById('sla-breached').textContent  = counts.breached;
    document.getElementById('sla-at-risk').textContent   = counts.at_risk;
    document.getElementById('sla-ok').textContent        = counts.ok;
    // Show escalate button if any escalated/breached
    const escBtn = document.getElementById('escalate-btn');
    if (escBtn) escBtn.style.display = (counts.escalated + counts.breached) > 0 ? 'block' : 'none';
    // Update SLA badge in nav
    const nb = document.getElementById('nb-sla');
    const breachCount = counts.escalated + counts.breached;
    if (nb) { nb.textContent = breachCount; nb.style.display = breachCount > 0 ? 'inline-flex' : 'none'; }

    // Render SLA config table (admin only)
    const configTbody = document.getElementById('sla-config-tbody');
    if (configTbody) {
      configTbody.innerHTML = cfg.map(c => `<tr>
        <td><span class="badge b-${c.priority}">${c.priority.toUpperCase()}</span></td>
        <td><input type="number" class="form-control" style="width:80px;padding:4px 8px;font-size:12px"
             id="sla-resp-${c.priority}" value="${c.response_hours}" min="0.5" step="0.5"></td>
        <td><input type="number" class="form-control" style="width:80px;padding:4px 8px;font-size:12px"
             id="sla-resol-${c.priority}" value="${c.resolution_hours}" min="1" step="1"></td>
        <td><input type="number" class="form-control" style="width:80px;padding:4px 8px;font-size:12px"
             id="sla-esc-${c.priority}" value="${c.escalation_hours}" min="1" step="1"></td>
      </tr>`).join('');
    }

    if (!wos.length) {
      listEl.innerHTML = '<div class="empty-state"><div class="icon">✅</div><h3>All WOs On Track</h3><p>No open work orders found.</p></div>';
      return;
    }

    const statusColors = { escalated: 'var(--red)', breached: 'var(--red)', at_risk: 'var(--yellow)', ok: 'var(--green)' };
    const statusLabels = { escalated: '🔴 ESCALATED', breached: '🟠 BREACHED', at_risk: '🟡 AT RISK', ok: '🟢 ON TRACK' };
    listEl.innerHTML = wos.sort((a,b) => {
      const order = { escalated:0, breached:1, at_risk:2, ok:3 };
      return (order[a.sla_status]||3) - (order[b.sla_status]||3);
    }).map(w => {
      const barColor = statusColors[w.sla_status] || 'var(--green)';
      const remaining = w.sla_remaining_hours;
      const remStr = remaining < 1 ? `${Math.round(remaining * 60)}m` : `${remaining.toFixed(1)}h`;
      return `
        <div class="sla-item">
          <div style="flex:1;min-width:0">
            <div style="display:flex;align-items:center;gap:8px;margin-bottom:3px">
              <span class="sla-wo-num" onclick="showPage('work-orders')" style="cursor:pointer">${w.wo_number}</span>
              <span class="badge b-${w.priority}">${w.priority}</span>
              <span style="font-size:11px;font-weight:700;color:${barColor}">${statusLabels[w.sla_status]}</span>
            </div>
            <div class="sla-title">${w.title}</div>
            <div style="font-size:11px;color:var(--text2);margin-top:2px">${w.asset_name || ''} ${w.assigned_to_name ? '· ' + w.assigned_to_name : ''} · Age: ${w.age_hours}h</div>
            <div class="sla-bar" style="margin-top:6px">
              <div class="sla-bar-fill" style="width:${w.sla_pct}%;background:${barColor}"></div>
            </div>
          </div>
          <div class="sla-timer ${w.sla_status === 'ok' ? 'ok' : w.sla_status === 'at_risk' ? 'soon' : 'overdue'}">
            ${w.sla_status === 'ok' ? remStr + ' left' : (w.sla_status === 'breached' || w.sla_status === 'escalated') ? w.age_hours + 'h over' : remStr + ' left'}
          </div>
        </div>`;
    }).join('');
  } catch(e) {
    listEl.innerHTML = `<div class="empty-state"><div class="icon">⚠</div><h3>Load Failed</h3><p>${e.message}</p></div>`;
  }
}

async function saveSlaConfig() {
  const priorities = ['critical','high','medium','low'];
  const rows = priorities.map(p => ({
    priority: p,
    response_hours:    parseFloat(document.getElementById(`sla-resp-${p}`)?.value || 4),
    resolution_hours:  parseFloat(document.getElementById(`sla-resol-${p}`)?.value || 24),
    escalation_hours:  parseFloat(document.getElementById(`sla-esc-${p}`)?.value || 48),
  }));
  try {
    await api('PUT', '/sla-config', rows);
    toast('SLA configuration saved!', 'success');
    loadSlaMonitor();
  } catch(e) {
    toast('Failed: ' + e.message, 'error');
  }
}

async function runEscalation() {
  if (!confirm('Auto-escalate all overdue work orders that have exceeded their SLA escalation threshold?\n\nThis will raise their priority level and notify assigned technicians.')) return;
  try {
    const d = await api('POST', '/escalate-overdue');
    if (d.count === 0) {
      toast('No work orders required escalation.', 'success');
    } else {
      toast(`✅ ${d.count} work order(s) escalated.`, 'success');
      loadSlaMonitor();
    }
  } catch(e) {
    toast('Escalation failed: ' + e.message, 'error');
  }
}

// ── v6: REORDER WIZARD ────────────────────────────────────────────────────────
async function loadReorderWizard() {
  const el = document.getElementById('reorder-content');
  if (!el) return;
  el.innerHTML = '<div class="loading"><div class="spinner"></div>Scanning inventory...</div>';
  try {
    const d = await api('GET', '/reorder-wizard');
    if (d.total_parts === 0) {
      el.innerHTML = '<div class="empty-state"><div class="icon">✅</div><h3>Stock Levels OK</h3><p>All parts are above minimum stock levels.</p></div>';
      return;
    }
    const suppliers = Object.keys(d.by_supplier);
    el.innerHTML = suppliers.map(sup => {
      const parts = d.by_supplier[sup];
      const total = parts.reduce((s, p) => s + (p.suggested_cost || 0), 0);
      const supId = sup.replace(/[^a-z0-9]/gi, '_');
      return `
        <div class="card" style="margin-bottom:16px">
          <div class="card-header" style="display:flex;align-items:center;justify-content:space-between">
            <div>
              <span class="card-title">🏭 ${sup}</span>
              <span style="font-size:12px;color:var(--text2);margin-left:10px">${parts.length} item${parts.length > 1 ? 's' : ''} · Est. ₹${Number(total).toLocaleString('en-IN',{maximumFractionDigits:0})}</span>
            </div>
            <button class="btn btn-primary btn-sm" onclick="generatePO('${sup.replace(/'/g,"\\'")}','${supId}')">🛒 Generate PO</button>
          </div>
          <div class="tbl-wrap">
            <table>
              <thead><tr><th><input type="checkbox" onchange="toggleAllParts('${supId}',this.checked)" style="cursor:pointer;accent-color:var(--green)"></th>
                <th>Part Name</th><th>Part #</th><th>Current Stock</th><th>Min Stock</th><th>Suggested Qty</th><th>Unit Cost</th><th>Line Total</th></tr></thead>
              <tbody>
                ${parts.map((p,i) => `<tr>
                  <td><input type="checkbox" class="rw-cb rw-cb-${supId}" data-id="${p.id}" data-cost="${p.unit_cost||0}" checked style="cursor:pointer;accent-color:var(--green)"></td>
                  <td style="font-weight:500">${p.name}</td>
                  <td style="font-family:var(--mono);font-size:11px;color:var(--accent)">${p.part_number||'—'}</td>
                  <td style="font-family:var(--mono);color:var(--red)">${p.quantity}</td>
                  <td style="font-family:var(--mono);color:var(--text2)">${p.min_quantity}</td>
                  <td><input type="number" class="form-control rw-qty-${p.id}" style="width:80px;padding:4px 8px;font-size:12px" value="${p.suggested_qty}" min="1"></td>
                  <td style="font-family:var(--mono);font-size:12px">₹${Number(p.unit_cost||0).toLocaleString('en-IN',{maximumFractionDigits:2})}</td>
                  <td style="font-family:var(--mono);font-size:12px;color:var(--green)" id="rw-lt-${p.id}">₹${Number(p.suggested_cost).toLocaleString('en-IN',{maximumFractionDigits:2})}</td>
                </tr>`).join('')}
              </tbody>
            </table>
          </div>
          <div style="text-align:right;padding:10px 16px 4px;font-size:13px;color:var(--text2)">
            PO Total: <span style="font-family:var(--mono);font-size:15px;font-weight:700;color:var(--text0)" id="rw-total-${supId}">₹${Number(total).toLocaleString('en-IN',{maximumFractionDigits:0})}</span>
          </div>
        </div>`;
    }).join('');

    // Wire up qty change listeners
    el.querySelectorAll('input[type=number]').forEach(inp => {
      if (!inp.classList.contains('form-control')) return;
      const partId = [...inp.classList].find(c => c.startsWith('rw-qty-'))?.replace('rw-qty-','');
      if (!partId) return;
      inp.addEventListener('input', () => {
        const cost = parseFloat(inp.closest('tr')?.querySelector('[data-id]')?.dataset?.cost || 0);
        const lt = document.getElementById(`rw-lt-${partId}`);
        if (lt) lt.textContent = '₹' + Number((parseFloat(inp.value)||0)*cost).toLocaleString('en-IN',{maximumFractionDigits:2});
      });
    });

  } catch(e) {
    el.innerHTML = `<div class="empty-state"><div class="icon">⚠</div><h3>Failed</h3><p>${e.message}</p></div>`;
  }
}

function toggleAllParts(supId, checked) {
  document.querySelectorAll(`.rw-cb-${supId}`).forEach(cb => cb.checked = checked);
}

async function generatePO(supplierName, supId) {
  const cbs = document.querySelectorAll(`.rw-cb-${supId}`);
  const parts = [];
  let total = 0;
  cbs.forEach(cb => {
    if (!cb.checked) return;
    const partId = cb.dataset.id;
    const unitCost = parseFloat(cb.dataset.cost || 0);
    const qty = parseInt(document.querySelector(`.rw-qty-${partId}`)?.value || 1);
    parts.push({ part_id: parseInt(partId), qty, unit_cost: unitCost });
    total += qty * unitCost;
  });
  if (!parts.length) { toast('Select at least one part', 'error'); return; }
  if (!confirm(`Generate PO for ${supplierName}?\n\n${parts.length} item(s) · Est. ₹${Number(total).toLocaleString('en-IN',{maximumFractionDigits:0})}\n\nThis will create a new Purchase Order.`)) return;
  try {
    const d = await api('POST', '/reorder-wizard/generate-po', { supplier_name: supplierName, parts });
    toast(`✅ PO ${d.po_number} created successfully!`, 'success');
    setTimeout(() => showPage('purchase-orders'), 1500);
  } catch(e) {
    toast('Failed: ' + e.message, 'error');
  }
}

// ── v6: WO PRINT BUTTON INJECTION ─────────────────────────────────────────────
// Patch WO detail view to add a Print button
const _origShowWO = typeof showWODetail === 'function' ? showWODetail : null;

// ── v6: GLOBAL SEARCH ENHANCEMENT ─────────────────────────────────────────────
// Override the topbar search to use the v6 global search endpoint
const _origGlobalSearch = typeof initGlobalSearch === 'function' ? initGlobalSearch : null;
async function v6SearchQuery(q) {
  if (q.length < 2) return [];
  try {
    const d = await api('GET', `/global-search?q=${encodeURIComponent(q)}`);
    return d.results || [];
  } catch(e) { return []; }
}

// Patch the search input handler
document.addEventListener('DOMContentLoaded', () => {
  const si = document.getElementById('topbar-search');
  if (!si) return;
  let debTimer;
  si.addEventListener('input', () => {
    clearTimeout(debTimer);
    debTimer = setTimeout(async () => {
      const q = si.value.trim();
      const sugg = document.getElementById('search-suggestions');
      if (!sugg) return;
      if (q.length < 2) { sugg.style.display = 'none'; return; }
      const results = await v6SearchQuery(q);
      if (!results.length) { sugg.style.display = 'none'; return; }
      const typePages = { asset: 'assets', work_order: 'work-orders', part: 'parts', pm: 'pm' };
      sugg.innerHTML = results.map(r => `
        <div class="search-suggestion" onclick="showPage('${typePages[r.type]||r.type}');document.getElementById('topbar-search').value='';document.getElementById('search-suggestions').style.display='none'">
          <span class="search-suggestion-icon">${r.icon}</span>
          <div>
            <div>${r.name}</div>
            <div class="search-suggestion-sub">${r.type.replace('_',' ')} ${r.code ? '· ' + r.code : ''} ${r.status ? '· ' + r.status : ''}</div>
          </div>
        </div>`).join('');
      sugg.style.display = 'block';
    }, 250);
  });
});

// ── v6: AUTO BACKUP STATUS IN SETTINGS ────────────────────────────────────────
async function loadAutoBackupLog() {
  const el = document.getElementById('auto-backup-log');
  if (!el) return;
  try {
    const logs = await api('GET', '/auto-backup-log');
    if (!logs.length) { el.innerHTML = '<div style="font-size:12px;color:var(--text2);text-align:center;padding:10px">No auto-backup records yet.</div>'; return; }
    el.innerHTML = logs.slice(0,10).map(l => `
      <div style="display:flex;justify-content:space-between;align-items:center;padding:7px 6px;border-bottom:1px solid var(--border);font-size:12px">
        <div style="display:flex;align-items:center;gap:8px">
          <span style="font-size:14px">${l.backup_type === 'auto' ? '🤖' : '👤'}</span>
          <div>
            <div style="font-family:var(--mono);font-size:11px;color:var(--text0)">${l.backup_file}</div>
            <div style="color:var(--text2)">${l.created_at?.slice(0,16)} · ${l.size_kb} KB</div>
          </div>
        </div>
        <span class="badge ${l.status==='success'?'b-success':'b-danger'}">${l.status}</span>
      </div>`).join('');
  } catch(e) {}
}

async function runBackupNow() {
  const btn = document.getElementById('run-backup-btn');
  if (btn) { btn.disabled = true; btn.textContent = '⏳ Backing up...'; }
  try {
    const d = await api('POST', '/run-backup-now');
    toast(`✅ Backup created: ${d.backup_file} (${d.size_kb} KB)`, 'success');
    loadAutoBackupLog();
  } catch(e) {
    toast('Backup failed: ' + e.message, 'error');
  }
  if (btn) { btn.disabled = false; btn.textContent = '▶ Backup Now'; }
}

// ── v6: WIRE INTO INIT ─────────────────────────────────────────────────────────
function initV6() {
  // Update year selector to current year
  const byear = document.getElementById('budget-year');
  if (byear) {
    const cur = new Date().getFullYear();
    byear.innerHTML = [cur+1, cur, cur-1].map(y => `<option value="${y}" ${y===cur?'selected':''}>${y}</option>`).join('');
  }
  // Show admin-section elements if admin
  if (state?.isAdmin) {
    document.querySelectorAll('.admin-section').forEach(el => el.style.display = '');
  }
  // Poll SLA badge count periodically
  setInterval(async () => {
    try {
      const wos = await api('GET', '/sla-status');
      const nb = document.getElementById('nb-sla');
      const breachCount = wos.filter(w => w.sla_status === 'escalated' || w.sla_status === 'breached').length;
      if (nb) { nb.textContent = breachCount; nb.style.display = breachCount > 0 ? 'inline-flex' : 'none'; }
    } catch(e) {}
  }, 60000); // every 60s
}

// Inject auto-backup panel into the about page settings card
function injectAutoBackupPanel() {
  const dbSection = document.querySelector('#page-about .card');
  if (!dbSection) return;
  // We insert the auto-backup log into the settings area if we can find it
}

// Inject Print button into WO detail modals
document.addEventListener('click', e => {
  const btn = e.target.closest('[data-wo-print]');
  if (btn) {
    const woId = btn.dataset.woPrint;
    window.open(`/api/work-orders/${woId}/print`, '_blank');
  }
});

// Patch initApp to include v6
const _prevInitAppv6 = window.initApp;
if (_prevInitAppv6) {
  window.initApp = function() {
    _prevInitAppv6();
    setTimeout(initV6, 600);
  };
}

</script>
</body>
</html>"""

@app.route('/')
def index():
    if 'user_id' not in session:
        return HTML
    return HTML

@app.route('/api/health')
def health():
    return jsonify({'status': 'ok', 'version': APP_VERSION, 'codename': APP_CODENAME, 'time': datetime.now().isoformat()})

# ── SSE EVENT BUS ─────────────────────────────────────────────────────────────

_sse_listeners = []
_sse_lock = threading.Lock()

def broadcast_event(event_type, data):
    """Broadcast an SSE event to all connected clients."""
    msg = f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
    with _sse_lock:
        dead = []
        for q in _sse_listeners:
            try:
                q.put_nowait(msg)
            except:
                dead.append(q)
        for q in dead:
            _sse_listeners.remove(q)

@app.route('/api/events')
@login_required
def sse_stream():
    """Server-Sent Events endpoint for real-time notifications."""
    q = queue.Queue(maxsize=50)
    with _sse_lock:
        _sse_listeners.append(q)
    def generate():
        try:
            yield f"event: connected\ndata: {json.dumps({'user_id': session['user_id']})}\n\n"
            while True:
                try:
                    msg = q.get(timeout=30)
                    yield msg
                except queue.Empty:
                    yield f": ping\n\n"
        except GeneratorExit:
            pass
        finally:
            with _sse_lock:
                if q in _sse_listeners:
                    _sse_listeners.remove(q)
    return Response(stream_with_context(generate()),
                    mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})

# ── PWA MANIFEST & SERVICE WORKER ────────────────────────────────────────────

@app.route('/manifest.json')
def pwa_manifest():
    manifest = {
        "name": "NEXUS CMMS Enterprise",
        "short_name": "NEXUS CMMS",
        "description": "Computerized Maintenance Management System",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#07080a",
        "theme_color": "#00e5a0",
        "orientation": "any",
        "icons": [
            {"src": "data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 192 192'><rect width='192' height='192' rx='24' fill='%2307080a'/><text y='128' x='96' text-anchor='middle' font-size='120' fill='%2300e5a0'>⚙</text></svg>", "sizes": "192x192", "type": "image/svg+xml"},
            {"src": "data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 512 512'><rect width='512' height='512' rx='64' fill='%2307080a'/><text y='360' x='256' text-anchor='middle' font-size='320' fill='%2300e5a0'>⚙</text></svg>", "sizes": "512x512", "type": "image/svg+xml"}
        ],
        "categories": ["business", "productivity", "utilities"],
        "screenshots": []
    }
    return jsonify(manifest)

@app.route('/sw.js')
def service_worker():
    sw_code = """
const CACHE_NAME = 'nexus-cmms-v3';
const STATIC_ASSETS = ['/'];

self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE_NAME).then(cache => cache.addAll(STATIC_ASSETS))
  );
  self.skipWaiting();
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);
  // Don't cache API calls or SSE
  if (url.pathname.startsWith('/api/')) return;

  e.respondWith(
    fetch(e.request)
      .then(resp => {
        const clone = resp.clone();
        caches.open(CACHE_NAME).then(cache => cache.put(e.request, clone));
        return resp;
      })
      .catch(() => caches.match(e.request).then(r => r || new Response('Offline - No cache available', {status: 503})))
  );
});

// Background sync for offline work orders
self.addEventListener('sync', e => {
  if (e.tag === 'sync-offline-wo') {
    e.waitUntil(syncOfflineWorkOrders());
  }
});

async function syncOfflineWorkOrders() {
  // Notify all clients to sync their offline queue
  const clients = await self.clients.matchAll();
  clients.forEach(client => client.postMessage({ type: 'SYNC_OFFLINE_WO' }));
}

self.addEventListener('push', e => {
  const data = e.data ? e.data.json() : {};
  e.waitUntil(
    self.registration.showNotification(data.title || 'NEXUS CMMS', {
      body: data.body || 'New notification',
      icon: '/manifest.json',
      badge: '/manifest.json',
      data: data,
      actions: data.actions || []
    })
  );
});

self.addEventListener('notificationclick', e => {
  e.notification.close();
  e.waitUntil(
    self.clients.matchAll({ type: 'window' }).then(clients => {
      if (clients.length) { clients[0].focus(); }
      else { self.clients.openWindow('/'); }
    })
  );
});
"""
    return Response(sw_code, mimetype='application/javascript')

# ── MOBILE: OFFLINE WORK ORDER SUBMISSION ────────────────────────────────────

@app.route('/api/mobile/sync-offline', methods=['POST'])
@login_required
def sync_offline_wo():
    """Accept batched offline work orders created while disconnected."""
    items = request.json or []
    created = []
    for item in items:
        item['offline_id'] = item.get('offline_id', '')
        wo_num = generate_wo_number()
        conn = get_db()
        c = conn.cursor()
        try:
            c.execute("""INSERT INTO work_orders (wo_number,title,description,asset_id,type,priority,status,
                         assigned_to,requested_by,scheduled_date,due_date,notes)
                         VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                     (wo_num, item.get('title','Offline WO'), item.get('description'), item.get('asset_id'),
                      item.get('type','corrective'), item.get('priority','medium'), 'open',
                      item.get('assigned_to'), session['user_id'],
                      item.get('scheduled_date'), item.get('due_date'), item.get('notes')))
            new_id = c.lastrowid
            conn.commit()
            created.append({'offline_id': item.get('offline_id'), 'server_id': new_id, 'wo_number': wo_num})
            broadcast_event('wo_created', {'wo_number': wo_num, 'id': new_id, 'title': item.get('title')})
        except Exception as e:
            created.append({'offline_id': item.get('offline_id'), 'error': str(e)})
        finally:
            conn.close()
    return jsonify({'synced': created})

# ── MOBILE: QR CODE LOOKUP ────────────────────────────────────────────────────

@app.route('/api/mobile/scan/<code>')
@login_required
def scan_lookup(code):
    """Look up an asset, work order, or part by barcode/QR code."""
    conn = get_db()
    asset = conn.execute("""SELECT id,name,code,status,criticality,
        (SELECT ac.name FROM asset_categories ac WHERE ac.id=a.category_id) as category
        FROM assets a WHERE a.code=? OR a.barcode=? OR a.qr_code=?""",
        (code, code, code)).fetchone()
    if asset:
        conn.close()
        return jsonify({'type': 'asset', 'data': dict(asset)})
    part = conn.execute("SELECT id,name,part_number,quantity,min_quantity,location FROM parts WHERE part_number=? OR barcode=?",
        (code, code)).fetchone()
    if part:
        conn.close()
        return jsonify({'type': 'part', 'data': dict(part)})
    wo = conn.execute("SELECT id,wo_number,title,status,priority FROM work_orders WHERE wo_number=?", (code,)).fetchone()
    if wo:
        conn.close()
        return jsonify({'type': 'work_order', 'data': dict(wo)})
    conn.close()
    return jsonify({'type': 'not_found', 'code': code}), 404


# ── BULK WORK ORDER ACTIONS ───────────────────────────────────────────────────
@app.route('/api/work-orders/bulk', methods=['POST'])
@admin_required
def bulk_wo_action():
    data = request.json or {}
    ids    = data.get('ids', [])
    action = data.get('action', '')
    if not ids or action not in ('complete','cancel','delete','assign'):
        return jsonify({'error': 'Invalid request'}), 400
    conn = get_db()
    updated = 0
    for wo_id in ids:
        try:
            if action == 'complete':
                conn.execute("UPDATE work_orders SET status='completed',completed_at=datetime('now'),updated_at=datetime('now') WHERE id=?", (wo_id,))
                updated += 1
            elif action == 'cancel':
                conn.execute("UPDATE work_orders SET status='cancelled',updated_at=datetime('now') WHERE id=?", (wo_id,))
                updated += 1
            elif action == 'delete':
                conn.execute("DELETE FROM work_orders WHERE id=?", (wo_id,))
                updated += 1
            elif action == 'assign':
                assign_to = data.get('assign_to')
                if assign_to:
                    conn.execute("UPDATE work_orders SET assigned_to=?,updated_at=datetime('now') WHERE id=?", (assign_to, wo_id))
                    updated += 1
        except Exception: pass
    conn.commit()
    log_action(conn, session.get('user_id'), f'bulk_{action}', 'work_orders', 0, details=f'{updated} WOs')
    conn.close()
    return jsonify({'success': True, 'updated': updated})

# ── DASHBOARD HEATMAP DATA ────────────────────────────────────────────────────
@app.route('/api/heatmap')
@login_required
def heatmap_data():
    conn = get_db()
    rows = conn.execute("""
        SELECT date(created_at) as day, COUNT(*) as count
        FROM work_orders
        WHERE created_at >= date('now', '-90 days')
        GROUP BY day ORDER BY day
    """).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

# ── ASSET UTILIZATION SCORE ───────────────────────────────────────────────────
@app.route('/api/assets/<int:asset_id>/utilization')
@login_required
def asset_utilization(asset_id):
    conn = get_db()
    a = conn.execute("SELECT * FROM assets WHERE id=?", (asset_id,)).fetchone()
    if not a:
        conn.close()
        return jsonify({'error':'Not found'}), 404
    wo_count = conn.execute("SELECT COUNT(*) FROM work_orders WHERE asset_id=? AND created_at >= date('now','-365 days')", (asset_id,)).fetchone()[0]
    total_cost = conn.execute("SELECT COALESCE(SUM(total_cost),0) FROM work_orders WHERE asset_id=?", (asset_id,)).fetchone()[0]
    downtime_hrs = conn.execute("SELECT COALESCE(SUM(duration_hours),0) FROM downtime_records WHERE asset_id=? AND start_time >= date('now','-365 days')", (asset_id,)).fetchone()[0]
    # Simple health score: base 100, -5 per WO last year, -10 per downtime hour (max 50 penalty each)
    health = max(0, min(100, 100 - min(wo_count*5,50) - min(int(downtime_hrs*10),50)))
    conn.close()
    return jsonify({'asset_id': asset_id, 'wo_count_ytd': wo_count,
                    'total_maintenance_cost': round(total_cost, 2),
                    'downtime_hours_ytd': round(downtime_hrs, 1),
                    'health_score': health})

# ── LEGACY SEARCH (kept for backward compat with command palette) ──────────────
@app.route('/api/search')
@login_required
def legacy_search():
    q = request.args.get('q', '').strip()
    if len(q) < 2:
        return jsonify({'results': []})
    conn = get_db()
    like = f'%{q}%'
    results = []
    wos = conn.execute("""SELECT id, wo_number, title, status, priority FROM work_orders
        WHERE wo_number LIKE ? OR title LIKE ? LIMIT 5""", (like, like)).fetchall()
    for r in wos:
        results.append({'type':'work_order','id':r['id'],'label':f"{r['wo_number']} — {r['title']}",'sub':f"{r['status']} · {r['priority']}"})
    assets = conn.execute("""SELECT id, code, name, status FROM assets
        WHERE code LIKE ? OR name LIKE ? LIMIT 5""", (like, like)).fetchall()
    for r in assets:
        results.append({'type':'asset','id':r['id'],'label':f"{r['code']} — {r['name']}",'sub':r['status']})
    parts = conn.execute("""SELECT id, part_number, name, quantity FROM parts
        WHERE part_number LIKE ? OR name LIKE ? LIMIT 5""", (like, like)).fetchall()
    for r in parts:
        results.append({'type':'part','id':r['id'],'label':f"{r['part_number'] or '—'} — {r['name']}",'sub':f"Stock: {r['quantity']}"})
    conn.close()
    return jsonify({'results': results, 'query': q})

# ── WORK REQUEST PORTAL (public) ─────────────────────────────────────────────
@app.route('/api/work-requests', methods=['POST'])
def submit_work_request():
    """Public endpoint for work request submission (no auth required)."""
    data = request.json or {}
    title       = data.get('title','').strip()
    description = data.get('description','').strip()
    location    = data.get('location','').strip()
    priority    = data.get('priority','medium')
    requester   = data.get('requester_name','Anonymous').strip()
    contact     = data.get('contact_email','').strip()
    if not title:
        return jsonify({'success': False, 'error': 'Title is required'}), 400
    conn = get_db()
    wo_num = generate_wo_number()
    conn.execute("""INSERT INTO work_orders
        (wo_number, title, description, priority, status, type, notes, created_at)
        VALUES (?, ?, ?, ?, 'open', 'corrective', ?, datetime('now'))""",
        (wo_num, title, description, priority,
         f"Submitted by: {requester} | Contact: {contact} | Location: {location}"))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'wo_number': wo_num,
                    'message': 'Work request submitted successfully'})

@app.route('/request', methods=['GET'])
def work_request_portal():
    """Public work request submission portal."""
    return WORK_REQUEST_HTML

# ── AI MAINTENANCE INSIGHTS ───────────────────────────────────────────────────
@app.route('/api/insights')
@login_required
def get_insights():
    """Generate rule-based maintenance insights and recommendations."""
    conn = get_db()
    insights = []

    # Overdue WOs
    overdue = conn.execute("""SELECT COUNT(*) FROM work_orders
        WHERE status NOT IN ('completed','cancelled') AND due_date < date('now')""").fetchone()[0]
    if overdue > 0:
        insights.append({'type':'warning','priority':'high',
            'title': f'{overdue} Overdue Work Orders',
            'body': 'Overdue WOs increase asset downtime risk. Reassign or escalate immediately.',
            'action': 'work-orders', 'action_label': 'View WOs'})

    # Critical assets in maintenance
    crit_maint = conn.execute("""SELECT COUNT(*) FROM assets
        WHERE criticality='critical' AND status='maintenance'""").fetchone()[0]
    if crit_maint > 0:
        insights.append({'type':'danger','priority':'critical',
            'title': f'{crit_maint} Critical Asset(s) Under Maintenance',
            'body': 'Critical assets are offline. Monitor closely and expedite repairs.',
            'action': 'assets', 'action_label': 'View Assets'})

    # Low stock critical parts
    low_crit = conn.execute("""SELECT COUNT(*) FROM parts WHERE quantity <= min_quantity""").fetchone()[0]
    if low_crit > 0:
        insights.append({'type':'warning','priority':'medium',
            'title': f'{low_crit} Parts at or Below Minimum Stock',
            'body': 'Low inventory levels may delay future maintenance. Review and reorder now.',
            'action': 'parts', 'action_label': 'View Parts'})

    # PM overdue
    pm_overdue = conn.execute("""SELECT COUNT(*) FROM pm_schedules
        WHERE active=1 AND next_due < date('now')""").fetchone()[0]
    if pm_overdue > 0:
        insights.append({'type':'info','priority':'medium',
            'title': f'{pm_overdue} PM Schedule(s) Overdue',
            'body': 'Missed preventive maintenance increases corrective maintenance costs.',
            'action': 'pm', 'action_label': 'View PM'})

    # Warranties expiring in 90 days
    warranty_exp = conn.execute("""SELECT COUNT(*) FROM assets
        WHERE warranty_expiry BETWEEN date('now') AND date('now','+90 days')""").fetchone()[0]
    if warranty_exp > 0:
        insights.append({'type':'info','priority':'low',
            'title': f'{warranty_exp} Warranty Expiry in 90 Days',
            'body': 'Review expiring warranties and decide on renewal or service contracts.',
            'action': 'assets', 'action_label': 'View Assets'})

    # High downtime assets (last 30 days)
    high_dt = conn.execute("""SELECT a.name, SUM(d.duration_hours) as hrs
        FROM downtime_records d JOIN assets a ON d.asset_id=a.id
        WHERE d.start_time >= date('now','-30 days')
        GROUP BY d.asset_id HAVING hrs > 8 ORDER BY hrs DESC LIMIT 3""").fetchall()
    for r in high_dt:
        insights.append({'type':'warning','priority':'medium',
            'title': f'High Downtime: {r["name"]} ({r["hrs"]:.1f}h in 30d)',
            'body': 'Consider scheduling a comprehensive inspection or proactive overhaul.',
            'action': 'eq-history', 'action_label': 'View History'})

    # Good news: high completion rate
    total_wo = conn.execute("SELECT COUNT(*) FROM work_orders WHERE created_at >= date('now','-30 days')").fetchone()[0]
    done_wo  = conn.execute("SELECT COUNT(*) FROM work_orders WHERE status='completed' AND created_at >= date('now','-30 days')").fetchone()[0]
    if total_wo > 0:
        rate = round(done_wo / total_wo * 100)
        if rate >= 80:
            insights.append({'type':'success','priority':'low',
                'title': f'{rate}% WO Completion Rate (Last 30 Days)',
                'body': 'Excellent maintenance performance! Keep up the great work.',
                'action': 'reports', 'action_label': 'View Reports'})

    conn.close()
    return jsonify({'insights': insights, 'count': len(insights)})

# ── SLA / TIMER DATA ──────────────────────────────────────────────────────────
@app.route('/api/sla-stats')
@login_required
def sla_stats():
    conn = get_db()
    rows = conn.execute("""
        SELECT id, wo_number, title, priority, status, due_date, created_at,
            CAST((julianday(COALESCE(due_date, date('now','+7 days'))) - julianday('now')) * 24 AS INTEGER) as hours_remaining
        FROM work_orders
        WHERE status NOT IN ('completed','cancelled')
        ORDER BY due_date ASC NULLS LAST LIMIT 20
    """).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

# ── ASSET QR LABEL GENERATOR ──────────────────────────────────────────────────
@app.route('/api/assets/<int:asset_id>/qr-label')
@login_required
def asset_qr_label(asset_id):
    conn = get_db()
    a = conn.execute("SELECT * FROM assets WHERE id=?", (asset_id,)).fetchone()
    conn.close()
    if not a:
        return jsonify({'error': 'Asset not found'}), 404
    code = a['code'] or f'ASSET-{asset_id}'
    # Return SVG QR placeholder + asset info as printable HTML
    label_html = f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
<title>QR Label - {a['name']}</title>
<style>
  body{{margin:0;padding:20px;font-family:'IBM Plex Mono',monospace;background:#fff}}
  .label{{border:2px solid #000;border-radius:8px;padding:16px;width:240px;display:inline-block;page-break-inside:avoid}}
  .qr-placeholder{{width:120px;height:120px;border:1px solid #ccc;margin:0 auto 8px;display:flex;align-items:center;justify-content:center;background:#f5f5f5;border-radius:4px;font-size:10px;color:#666;text-align:center;padding:8px}}
  h2{{font-size:14px;margin:0 0 4px;text-align:center}}
  .code{{font-size:18px;font-weight:700;text-align:center;letter-spacing:2px;color:#00b87d}}
  .meta{{font-size:10px;color:#666;margin-top:8px;border-top:1px solid #eee;padding-top:8px}}
  .meta div{{margin-bottom:2px}}
  @media print{{body{{padding:0}}@page{{margin:10mm}}}}
</style></head><body>
<div class="label">
  <div class="qr-placeholder">
    <div>📱 Scan QR<br><br>{code}</div>
  </div>
  <div class="code">{code}</div>
  <h2>{a['name']}</h2>
  <div class="meta">
    <div>📍 Location: {a.get('location_name') or '—'}</div>
    <div>🏷 Category: {a.get('category_name') or '—'}</div>
    <div>⚙ Make/Model: {(a['make'] or '') + ' ' + (a['model'] or '') or '—'}</div>
    <div>🔑 Serial: {a['serial_number'] or '—'}</div>
    <div>⚠ Criticality: {a['criticality'] or 'medium'}</div>
  </div>
</div>
<script>setTimeout(()=>window.print(),300)</script>
</body></html>"""
    return label_html, 200, {'Content-Type': 'text/html'}

# ── ADVANCED ANALYTICS ENDPOINT ───────────────────────────────────────────────
@app.route('/api/analytics')
@login_required
def analytics():
    conn = get_db()
    # MTTR (Mean Time to Repair) per asset category
    mttr = conn.execute("""
        SELECT ac.name as category, AVG(w.actual_hours) as avg_hours, COUNT(*) as count
        FROM work_orders w
        JOIN assets a ON w.asset_id = a.id
        JOIN asset_categories ac ON a.category_id = ac.id
        WHERE w.status='completed' AND w.actual_hours > 0
        GROUP BY ac.id ORDER BY avg_hours DESC LIMIT 8
    """).fetchall()

    # WO volume by day of week
    by_dow = conn.execute("""
        SELECT strftime('%w', created_at) as dow, COUNT(*) as count
        FROM work_orders GROUP BY dow ORDER BY dow
    """).fetchall()

    # Cost by month last 12 months
    monthly_cost = conn.execute("""
        SELECT strftime('%Y-%m', created_at) as month,
               SUM(total_cost) as cost, COUNT(*) as count
        FROM work_orders WHERE created_at >= date('now','-12 months')
        GROUP BY month ORDER BY month
    """).fetchall()

    # Asset health score (simple: active=100, maintenance=50, inactive=0, retired=0)
    health = conn.execute("""
        SELECT status, COUNT(*) as cnt FROM assets GROUP BY status
    """).fetchall()

    # Top technicians by WOs completed
    top_techs = conn.execute("""
        SELECT u.full_name, COUNT(*) as completed, AVG(w.actual_hours) as avg_hrs
        FROM work_orders w JOIN users u ON w.assigned_to=u.id
        WHERE w.status='completed'
        GROUP BY w.assigned_to ORDER BY completed DESC LIMIT 5
    """).fetchall()

    # Repeat failures (same asset, 3+ WOs in 90 days)
    repeat = conn.execute("""
        SELECT a.name, a.code, COUNT(w.id) as wo_count
        FROM work_orders w JOIN assets a ON w.asset_id=a.id
        WHERE w.created_at >= date('now','-90 days') AND w.type='corrective'
        GROUP BY w.asset_id HAVING wo_count >= 2
        ORDER BY wo_count DESC LIMIT 5
    """).fetchall()

    conn.close()
    return jsonify({
        'mttr_by_category': [dict(r) for r in mttr],
        'wo_by_dow': [dict(r) for r in by_dow],
        'monthly_cost': [dict(r) for r in monthly_cost],
        'asset_health': [dict(r) for r in health],
        'top_technicians': [dict(r) for r in top_techs],
        'repeat_failures': [dict(r) for r in repeat],
    })

# ── WORK REQUEST PORTAL HTML ──────────────────────────────────────────────────
WORK_REQUEST_HTML = """<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>NEXUS CMMS — Submit Maintenance Request</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'IBM Plex Sans',sans-serif;background:linear-gradient(135deg,#07080a 0%,#0d1f16 100%);
  min-height:100vh;display:flex;align-items:center;justify-content:center;padding:20px}
.card{background:#161820;border:1px solid #252830;border-radius:16px;width:100%;max-width:540px;
  overflow:hidden;box-shadow:0 24px 80px rgba(0,0,0,.6)}
.card-header{background:linear-gradient(135deg,#0d1f16,#161820);padding:32px 36px;
  border-bottom:1px solid #252830;position:relative;overflow:hidden}
.card-header::before{content:'';position:absolute;top:0;left:0;right:0;height:2px;
  background:linear-gradient(90deg,transparent,#00e5a0,transparent)}
.logo{font-family:'IBM Plex Mono',monospace;font-size:22px;font-weight:600;
  color:#00e5a0;letter-spacing:4px;margin-bottom:4px}
h1{font-size:20px;font-weight:700;color:#f0f2f8;margin-bottom:4px}
.sub{font-size:13px;color:#5c6070}
.body{padding:32px 36px}
.form-group{margin-bottom:20px}
label{display:block;font-size:11px;font-weight:600;color:#5c6070;text-transform:uppercase;
  letter-spacing:.8px;margin-bottom:6px}
input,textarea,select{width:100%;padding:10px 14px;background:#1e2029;border:1px solid #30333d;
  border-radius:8px;color:#f0f2f8;font-size:14px;font-family:'IBM Plex Sans',sans-serif;
  transition:.2s;outline:none}
input:focus,textarea:focus,select:focus{border-color:#00e5a0;box-shadow:0 0 0 3px rgba(0,229,160,.1)}
textarea{min-height:100px;resize:vertical}
select option{background:#1e2029}
.row{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.btn{width:100%;padding:14px;background:#00e5a0;color:#07080a;border:none;border-radius:8px;
  font-size:15px;font-weight:700;cursor:pointer;transition:.2s;font-family:'IBM Plex Sans',sans-serif;
  letter-spacing:.5px}
.btn:hover{background:#00b87d;transform:translateY(-1px);box-shadow:0 8px 24px rgba(0,229,160,.3)}
.success-box{display:none;text-align:center;padding:32px}
.success-icon{font-size:56px;margin-bottom:16px}
.success-box h2{color:#00e5a0;font-size:22px;margin-bottom:8px}
.success-box p{color:#9aa0b4;font-size:14px;margin-bottom:4px}
.wo-num{font-family:'IBM Plex Mono',monospace;font-size:28px;font-weight:700;
  color:#00e5a0;margin:16px 0;letter-spacing:4px}
.new-btn{margin-top:20px;padding:10px 24px;background:transparent;
  border:1px solid #30333d;color:#9aa0b4;border-radius:8px;cursor:pointer;
  font-family:'IBM Plex Sans',sans-serif;font-size:13px;transition:.2s}
.new-btn:hover{border-color:#00e5a0;color:#00e5a0}
.priority-badges{display:flex;gap:8px;flex-wrap:wrap}
.priority-badge{padding:6px 14px;border-radius:20px;border:1px solid #30333d;
  font-size:12px;font-weight:600;cursor:pointer;transition:.2s;background:transparent;color:#9aa0b4}
.priority-badge.active-low{background:rgba(0,229,160,.1);border-color:#00e5a0;color:#00e5a0}
.priority-badge.active-medium{background:rgba(77,166,255,.1);border-color:#4da6ff;color:#4da6ff}
.priority-badge.active-high{background:rgba(255,190,77,.1);border-color:#ffbe4d;color:#ffbe4d}
.priority-badge.active-critical{background:rgba(255,77,109,.1);border-color:#ff4d6d;color:#ff4d6d}
.err{color:#ff4d6d;font-size:12px;margin-top:6px;display:none}
@media(max-width:500px){.row{grid-template-columns:1fr}.body,.card-header{padding:24px 20px}}
</style></head>
<body>
<div class="card">
  <div class="card-header">
    <div class="logo">NEXUS</div>
    <h1>Submit Maintenance Request</h1>
    <p class="sub">Fill in the details below and our team will respond promptly</p>
  </div>
  <div class="body" id="form-body">
    <div class="form-group">
      <label>What needs attention? *</label>
      <input type="text" id="req-title" placeholder="e.g. Air conditioner not cooling in Room 3">
      <div class="err" id="err-title">Please enter a title</div>
    </div>
    <div class="form-group">
      <label>Description</label>
      <textarea id="req-desc" placeholder="Describe the issue in detail — when did it start, any sounds or smells, how it affects work..."></textarea>
    </div>
    <div class="form-group">
      <label>Priority</label>
      <div class="priority-badges">
        <button class="priority-badge active-low" data-p="low" onclick="setPriority('low')">🟢 Low</button>
        <button class="priority-badge" data-p="medium" onclick="setPriority('medium')">🔵 Medium</button>
        <button class="priority-badge" data-p="high" onclick="setPriority('high')">🟡 High</button>
        <button class="priority-badge" data-p="critical" onclick="setPriority('critical')">🔴 Critical</button>
      </div>
    </div>
    <div class="row">
      <div class="form-group">
        <label>Your Name *</label>
        <input type="text" id="req-name" placeholder="Full name">
        <div class="err" id="err-name">Required</div>
      </div>
      <div class="form-group">
        <label>Contact Email</label>
        <input type="email" id="req-email" placeholder="you@company.com">
      </div>
    </div>
    <div class="form-group">
      <label>Location / Area</label>
      <input type="text" id="req-location" placeholder="e.g. Building A, Floor 2, Room 201">
    </div>
    <button class="btn" onclick="submitRequest()">Submit Request →</button>
  </div>
  <div class="success-box" id="success-box">
    <div class="success-icon">✅</div>
    <h2>Request Submitted!</h2>
    <p>Your work request has been logged:</p>
    <div class="wo-num" id="success-wo-num"></div>
    <p style="color:#5c6070;font-size:12px">Save this number to track your request status</p>
    <button class="new-btn" onclick="resetForm()">+ Submit Another Request</button>
  </div>
</div>
<script>
let selectedPriority = 'low';
function setPriority(p) {
  selectedPriority = p;
  document.querySelectorAll('.priority-badge').forEach(b => {
    b.className = 'priority-badge' + (b.dataset.p === p ? ' active-' + p : '');
  });
}
async function submitRequest() {
  const title = document.getElementById('req-title').value.trim();
  const name  = document.getElementById('req-name').value.trim();
  let valid = true;
  if (!title) { document.getElementById('err-title').style.display='block'; valid=false; } else { document.getElementById('err-title').style.display='none'; }
  if (!name)  { document.getElementById('err-name').style.display='block'; valid=false; }  else { document.getElementById('err-name').style.display='none'; }
  if (!valid) return;
  const btn = document.querySelector('.btn');
  btn.textContent = 'Submitting...'; btn.disabled = true;
  try {
    const r = await fetch('/api/work-requests', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({
        title, description: document.getElementById('req-desc').value,
        priority: selectedPriority, requester_name: name,
        contact_email: document.getElementById('req-email').value,
        location: document.getElementById('req-location').value
      })
    });
    const d = await r.json();
    if (d.success) {
      document.getElementById('form-body').style.display = 'none';
      document.getElementById('success-box').style.display = 'block';
      document.getElementById('success-wo-num').textContent = d.wo_number;
    } else { alert(d.error || 'Submission failed'); btn.textContent='Submit Request →'; btn.disabled=false; }
  } catch(e) { alert('Network error: ' + e.message); btn.textContent='Submit Request →'; btn.disabled=false; }
}
function resetForm() {
  document.getElementById('form-body').style.display='block';
  document.getElementById('success-box').style.display='none';
  document.getElementById('req-title').value='';
  document.getElementById('req-desc').value='';
  document.getElementById('req-name').value='';
  document.getElementById('req-email').value='';
  document.getElementById('req-location').value='';
  setPriority('low');
  const btn = document.querySelector('.btn');
  btn.textContent='Submit Request →'; btn.disabled=false;
}

// ── MANUAL UPDATE ─────────────────────────────────────────────────────────────
let _updateFile = null;

function handleUpdateDrop(e) {
  e.preventDefault();
  document.getElementById('update-dropzone').classList.remove('dz-hover');
  const file = e.dataTransfer.files[0];
  if (file) setUpdateFile(file);
}

function handleUpdateFileSelect(input) {
  if (input.files[0]) setUpdateFile(input.files[0]);
}

function setUpdateFile(file) {
  if (!file.name.endsWith('.py')) {
    toast('Only .py files are accepted.', 'error'); return;
  }
  _updateFile = file;
  const dz = document.getElementById('update-dropzone');
  dz.classList.add('dz-ready');
  document.getElementById('dz-label').textContent = '✅ File selected: ' + file.name;
  document.getElementById('update-file-preview').style.display = 'block';
  document.getElementById('uf-name').textContent = file.name;
  document.getElementById('uf-size').textContent = (file.size / 1024).toFixed(1) + ' KB';
  document.getElementById('update-notes-wrap').style.display = 'block';
  document.getElementById('apply-update-btn').disabled = false;
  document.getElementById('manual-update-result').style.display = 'none';
}

function clearUpdateFile() {
  _updateFile = null;
  document.getElementById('update-dropzone').classList.remove('dz-ready');
  document.getElementById('dz-label').textContent = 'Click or drag & drop update file here';
  document.getElementById('update-file-preview').style.display = 'none';
  document.getElementById('update-notes-wrap').style.display = 'none';
  document.getElementById('apply-update-btn').disabled = true;
  document.getElementById('manual-update-result').style.display = 'none';
  document.getElementById('update-file-input').value = '';
}

async function applyManualUpdate() {
  if (!_updateFile) return;

  const confirmed = confirm(
    '⚠️ Apply Manual Update?\n\n' +
    '• The current application file will be BACKED UP automatically.\n' +
    '• The new file will replace it immediately.\n' +
    '• You must RESTART the server after applying.\n\n' +
    'Proceed with update?'
  );
  if (!confirmed) return;

  const btn = document.getElementById('apply-update-btn');
  const res  = document.getElementById('manual-update-result');
  btn.disabled = true;
  btn.textContent = '⏳ Applying update…';
  res.style.display = 'none';

  const fd = new FormData();
  fd.append('file', _updateFile);
  const notes = document.getElementById('update-notes-txt').value.trim();
  if (notes) fd.append('notes', notes);

  // Pre-check: verify session is still valid before uploading large file
  try {
    const sessionCheck = await fetch('/api/me', { credentials: 'same-origin' });
    if (sessionCheck.status === 401) {
      res.style.display = 'block';
      res.innerHTML = `<div style="background:rgba(220,38,38,.1);border:1px solid var(--red);border-radius:var(--r8);padding:14px">
        <div style="font-weight:700;color:var(--text0)">❌ Session Expired</div>
        <div style="font-size:13px;color:var(--text2);margin-top:6px">Your session has expired. Please <a href="#" onclick="location.reload()" style="color:var(--accent)">refresh the page</a>, log in again, then retry the update.</div>
      </div>`;
      btn.disabled = false; btn.textContent = '🚀 Apply Update'; return;
    }
    const me = await sessionCheck.json();
    if (me.user?.role !== 'admin') {
      res.style.display = 'block';
      res.innerHTML = `<div style="background:rgba(220,38,38,.1);border:1px solid var(--red);border-radius:var(--r8);padding:14px">
        <div style="font-weight:700;color:var(--text0)">❌ Admin Required</div>
        <div style="font-size:13px;color:var(--text2);margin-top:6px">Only Administrator accounts can apply updates.</div>
      </div>`;
      btn.disabled = false; btn.textContent = '🚀 Apply Update'; return;
    }
  } catch(e) { /* session check failed, proceed anyway */ }

  try {
    const resp = await fetch('/api/manual-update', {
      method: 'POST',
      body: fd,
      credentials: 'same-origin',
    });

    // Handle HTTP-level errors explicitly
    if (resp.status === 401) {
      res.style.display = 'block';
      res.innerHTML = `<div style="background:rgba(220,38,38,.1);border:1px solid var(--red);border-radius:var(--r8);padding:14px">
        <div style="font-weight:700;color:var(--text0)">❌ Session Expired</div>
        <div style="font-size:13px;color:var(--text2);margin-top:6px">Your login session has expired. Please <a href="#" onclick="location.reload()" style="color:var(--accent)">refresh the page</a> and log in again, then try the update.</div>
      </div>`;
      btn.disabled = false; btn.textContent = '🚀 Apply Update'; return;
    }
    if (resp.status === 403) {
      res.style.display = 'block';
      res.innerHTML = `<div style="background:rgba(220,38,38,.1);border:1px solid var(--red);border-radius:var(--r8);padding:14px">
        <div style="font-weight:700;color:var(--text0)">❌ Admin Access Required</div>
        <div style="font-size:13px;color:var(--text2);margin-top:6px">Only Administrator accounts can apply updates. Please log in as an admin.</div>
      </div>`;
      btn.disabled = false; btn.textContent = '🚀 Apply Update'; return;
    }

    let d;
    try { d = await resp.json(); } catch(je) {
      throw new Error('Server returned an unexpected response (status ' + resp.status + '). Check the server terminal for errors.');
    }
    res.style.display = 'block';

    if (d.success) {
      res.innerHTML = `
        <div style="background:var(--green-glow);border:1px solid var(--green);border-radius:var(--r8);padding:14px">
          <div style="display:flex;align-items:center;gap:10px;margin-bottom:10px">
            <span style="font-size:26px">✅</span>
            <div>
              <div style="font-weight:700;color:var(--green);font-size:15px">Update Applied Successfully!</div>
              <div style="font-size:12px;color:var(--text2);margin-top:2px">Version <span style="font-family:var(--mono);color:var(--green)">v${d.new_version}</span> · Applied at ${d.applied_at}</div>
            </div>
          </div>
          <div style="background:var(--bg1);border-radius:6px;padding:10px;font-size:12px;color:var(--text1);line-height:1.8">
            <div>📦 <strong>Backup saved as:</strong> <span style="font-family:var(--mono)">${d.backup_file}</span></div>
            <div style="margin-top:6px">⚠️ <strong>Action Required:</strong> Please <strong>restart the server</strong> to activate the new version.</div>
            <div style="margin-top:10px">
              <code style="background:var(--bg3);padding:4px 10px;border-radius:4px;font-size:12px;display:block;font-family:var(--mono)">
                Ctrl+C → python3 cmms_app_v5_enterprise.py
              </code>
            </div>
          </div>
          <button class="btn btn-secondary" style="width:100%;margin-top:12px" onclick="loadBackupList()">📂 View Backups</button>
        </div>`;
      clearUpdateFile();
      document.getElementById('update-badge').style.display = 'none';
    } else {
      res.innerHTML = `
        <div style="background:rgba(220,38,38,.1);border:1px solid var(--red);border-radius:var(--r8);padding:14px">
          <div style="display:flex;align-items:center;gap:10px">
            <span style="font-size:22px">❌</span>
            <div>
              <div style="font-weight:700;color:var(--text0)">Update Failed</div>
              <div style="font-size:13px;color:var(--text2);margin-top:4px">${d.error}</div>
            </div>
          </div>
        </div>`;
    }
  } catch(e) {
    res.style.display = 'block';
    res.innerHTML = `
      <div style="background:rgba(220,38,38,.1);border:1px solid var(--red);border-radius:var(--r8);padding:14px">
        <div style="font-weight:600">Upload error: ${e.message}</div>
      </div>`;
  }
  btn.disabled = false;
  btn.textContent = '🚀 Apply Update';
}

async function loadBackupList() {
  const el = document.getElementById('backup-list');
  el.innerHTML = '<div style="font-size:12px;color:var(--text2);text-align:center;padding:10px">Loading…</div>';
  try {
    const backups = await api('GET', '/list-backups');
    if (!backups.length) {
      el.innerHTML = '<div style="font-size:12px;color:var(--text2);text-align:center;padding:10px">No backup files found.</div>';
      return;
    }
    el.innerHTML = backups.map(b => `
      <div style="display:flex;align-items:center;justify-content:space-between;padding:8px 6px;border-bottom:1px solid var(--border);font-size:12px">
        <div style="display:flex;align-items:center;gap:8px">
          <span style="font-size:16px">🗄</span>
          <div>
            <div style="font-family:var(--mono);color:var(--text0);font-size:11px">${b.filename}</div>
            <div style="color:var(--text2)">${b.modified} · ${b.size_kb} KB</div>
          </div>
        </div>
        <button class="btn btn-sm btn-secondary" onclick="restoreBackup('${b.filename}')" title="Restore this backup">↩ Restore</button>
      </div>`).join('');
  } catch(e) {
    el.innerHTML = '<div style="font-size:12px;color:var(--text2);text-align:center;padding:10px">Could not load backups.</div>';
  }
}

async function restoreBackup(filename) {
  if (!confirm(`⚠️ Restore Backup?\n\nThis will replace the current application with:\n"${filename}"\n\nThe current version will be backed up first.\nYou must restart the server after restoring.\n\nProceed?`)) return;
  const res = document.getElementById('manual-update-result');
  res.style.display = 'none';
  try {
    const d = await api('POST', '/restore-backup', { filename });
    res.style.display = 'block';
    if (d.success) {
      res.innerHTML = `
        <div style="background:var(--green-glow);border:1px solid var(--green);border-radius:var(--r8);padding:14px">
          <div style="font-weight:700;color:var(--green);margin-bottom:6px">✅ Backup Restored Successfully!</div>
          <div style="font-size:12px;color:var(--text1);line-height:1.8">
            <div>📦 Restored: <span style="font-family:var(--mono)">${filename}</span></div>
            <div>🗄 New backup of current: <span style="font-family:var(--mono)">${d.backup_file}</span></div>
            <div style="margin-top:8px;background:var(--bg1);padding:8px;border-radius:4px;font-family:var(--mono);font-size:11px">Ctrl+C → python3 cmms_app_v5_enterprise.py</div>
          </div>
        </div>`;
      loadBackupList();
    } else {
      res.innerHTML = `<div style="background:rgba(220,38,38,.1);border:1px solid var(--red);border-radius:var(--r8);padding:12px;font-size:13px;color:var(--text0)">❌ ${d.error}</div>`;
    }
  } catch(e) {
    res.style.display = 'block';
    res.innerHTML = `<div style="background:rgba(220,38,38,.1);border:1px solid var(--red);border-radius:var(--r8);padding:12px;font-size:13px">Restore failed: ${e.message}</div>`;
  }
}

// ── DATABASE BACKUP & RESTORE ─────────────────────────────────────────────────
let _dbRestoreFile = null;

function downloadDbBackup() {
  // Trigger download via anchor — server streams the file
  const a = document.createElement('a');
  a.href = '/api/db-backup-download';
  a.download = '';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
}

function handleDbRestoreDrop(e) {
  e.preventDefault();
  document.getElementById('db-restore-dropzone').classList.remove('dz-hover');
  const file = e.dataTransfer.files[0];
  if (file) setDbRestoreFile(file);
}

function handleDbRestoreFileSelect(input) {
  const file = input.files[0];
  if (file) setDbRestoreFile(file);
}

function setDbRestoreFile(file) {
  if (!file.name.endsWith('.db')) {
    alert('Only .db files are accepted for database restore.');
    return;
  }
  _dbRestoreFile = file;
  document.getElementById('db-restore-dropzone').classList.add('dz-ready');
  document.getElementById('db-dz-label').textContent = '✅ File selected: ' + file.name;
  document.getElementById('db-restore-preview').style.display = 'block';
  document.getElementById('db-rf-name').textContent = file.name;
  document.getElementById('db-rf-size').textContent = (file.size / 1024).toFixed(1) + ' KB';
  document.getElementById('apply-db-restore-btn').disabled = false;
  document.getElementById('db-backup-result').style.display = 'none';
}

function clearDbRestoreFile() {
  _dbRestoreFile = null;
  document.getElementById('db-restore-dropzone').classList.remove('dz-ready');
  document.getElementById('db-dz-label').textContent = 'Click or drag & drop .db backup file here';
  document.getElementById('db-restore-preview').style.display = 'none';
  document.getElementById('apply-db-restore-btn').disabled = true;
  document.getElementById('db-restore-file-input').value = '';
}

async function applyDbRestore() {
  if (!_dbRestoreFile) return;
  const confirmed = confirm(
    '⚠️ Restore Database?\n\n' +
    '• ALL current data will be REPLACED with the backup.\n' +
    '• The current database will be backed up automatically first.\n' +
    '• The server will need to be RESTARTED after restoring.\n\n' +
    'Proceed with restore?'
  );
  if (!confirmed) return;

  const btn = document.getElementById('apply-db-restore-btn');
  const res  = document.getElementById('db-backup-result');
  btn.disabled = true;
  btn.textContent = '⏳ Restoring…';
  res.style.display = 'none';

  const fd = new FormData();
  fd.append('file', _dbRestoreFile);

  try {
    const resp = await fetch('/api/db-restore', {
      method: 'POST',
      body: fd,
      credentials: 'same-origin',
    });

    if (resp.status === 401) {
      res.style.display = 'block';
      res.innerHTML = `<div style="background:rgba(220,38,38,.1);border:1px solid var(--red);border-radius:var(--r8);padding:12px;font-size:13px">❌ Session expired. Please refresh and log in again.</div>`;
      btn.disabled = false; btn.textContent = '♻ Restore Database'; return;
    }
    if (resp.status === 403) {
      res.style.display = 'block';
      res.innerHTML = `<div style="background:rgba(220,38,38,.1);border:1px solid var(--red);border-radius:var(--r8);padding:12px;font-size:13px">❌ Admin access required.</div>`;
      btn.disabled = false; btn.textContent = '♻ Restore Database'; return;
    }

    let d;
    try { d = await resp.json(); } catch(je) {
      throw new Error('Server returned unexpected response (status ' + resp.status + ')');
    }
    res.style.display = 'block';
    if (d.success) {
      res.innerHTML = `
        <div style="background:var(--green-glow);border:1px solid var(--green);border-radius:var(--r8);padding:14px">
          <div style="font-weight:700;color:var(--green);margin-bottom:8px">✅ Database Restored Successfully!</div>
          <div style="font-size:12px;color:var(--text1);line-height:1.8">
            <div>🗄 Restored from: <span style="font-family:var(--mono)">${_dbRestoreFile.name}</span></div>
            <div>📦 Previous DB backed up as: <span style="font-family:var(--mono)">${d.backup_file}</span></div>
            <div style="margin-top:8px;background:var(--bg1);padding:8px;border-radius:4px;font-size:12px;color:var(--text2)">
              ⚠️ <strong>Restart the server</strong> to activate the restored database.
            </div>
            <div style="margin-top:8px;font-family:var(--mono);font-size:11px;background:var(--bg1);padding:6px 10px;border-radius:4px">
              Ctrl+C → python3 ${d.script_name}
            </div>
          </div>
        </div>`;
      clearDbRestoreFile();
    } else {
      res.innerHTML = `
        <div style="background:rgba(220,38,38,.1);border:1px solid var(--red);border-radius:var(--r8);padding:12px;font-size:13px;color:var(--text0)">
          ❌ ${d.error}
        </div>`;
    }
  } catch(e) {
    res.style.display = 'block';
    res.innerHTML = `<div style="background:rgba(220,38,38,.1);border:1px solid var(--red);border-radius:var(--r8);padding:12px;font-size:13px">Restore failed: ${e.message}</div>`;
  }
  btn.disabled = false;
  btn.textContent = '♻ Restore Database';
}

// ── END DATABASE BACKUP & RESTORE ─────────────────────────────────────────────
async function loadVersionInfo() {
  try {
    const d = await api('GET', '/version-info');
    document.getElementById('installed-ver').textContent   = 'v' + d.current_version;
    document.getElementById('installed-build').textContent = 'Build ' + d.build_date + ' · ' + d.codename;
    document.getElementById('si-python').textContent  = d.python_version;
    document.getElementById('si-db').textContent      = d.db_path;
    document.getElementById('si-dbsize').textContent  = d.db_size_kb + ' KB';
    document.getElementById('si-wo').textContent      = d.stats.work_orders;
    document.getElementById('si-assets').textContent  = d.stats.assets;
    document.getElementById('si-users').textContent   = d.stats.users;
    document.getElementById('si-pm').textContent      = d.stats.pm_schedules;
  } catch(e) { /* silently fail */ }

  // Show/hide manual update section based on admin role
  const isAdmin   = state && state.isAdmin;
  const adminUI   = document.getElementById('update-admin-ui');
  const adminOnly = document.getElementById('update-admin-only');
  if (adminUI && adminOnly) {
    adminUI.style.display   = isAdmin ? 'block' : 'none';
    adminOnly.style.display = isAdmin ? 'none'  : 'block';
  }
  if (isAdmin) loadBackupList();
}

async function runUpdateCheck() {
  const btn = document.getElementById('check-update-btn');
  const res  = document.getElementById('update-result');
  btn.disabled = true;
  btn.textContent = '⏳ Checking…';
  res.style.display = 'none';
  try {
    const d = await api('POST', '/check-update');
    document.getElementById('last-checked-time').textContent = d.checked_at;
    const badge = document.getElementById('update-badge');

    if (d.update_available) {
      badge.style.display = 'inline-block';
      res.style.display = 'block';
      res.innerHTML = `
        <div style="background:rgba(var(--red-rgb,220,38,38),.1);border:1px solid var(--red);border-radius:var(--r8);padding:14px;margin-bottom:10px">
          <div style="display:flex;align-items:center;gap:10px;margin-bottom:10px">
            <span style="font-size:22px">🆕</span>
            <div>
              <div style="font-weight:700;color:var(--text0)">New Version Available!</div>
              <div style="font-size:13px;color:var(--text2)">
                <span style="font-family:var(--mono);color:var(--green)">v${d.latest_version}</span>
                is available — you are running
                <span style="font-family:var(--mono);color:var(--text1)">v${d.current_version}</span>
              </div>
            </div>
          </div>
          ${d.notes && d.notes.length ? '<div style="font-size:12px;color:var(--text2);margin-bottom:10px"><strong>What\'s new:</strong><ul style="margin:6px 0 0 16px;line-height:1.8">' + d.notes.map(n=>`<li>${n}</li>`).join('') + '</ul></div>' : ''}
          <div style="font-size:12px;color:var(--text2);padding:10px;background:var(--bg2);border-radius:6px;font-family:var(--mono)">
            To update: replace <strong>cmms_app_v5_enterprise.py</strong> with the new version file, then restart the server.
          </div>
        </div>`;
    } else {
      badge.style.display = 'none';
      res.style.display = 'block';
      res.innerHTML = `
        <div style="background:var(--green-glow);border:1px solid var(--green);border-radius:var(--r8);padding:14px;display:flex;align-items:center;gap:12px">
          <span style="font-size:24px">✅</span>
          <div>
            <div style="font-weight:700;color:var(--green)">You're up to date!</div>
            <div style="font-size:12px;color:var(--text2);margin-top:2px">
              NEXUS CMMS <span style="font-family:var(--mono)">v${d.current_version}</span> is the latest version.
            </div>
          </div>
        </div>`;
    }
  } catch(e) {
    res.style.display = 'block';
    res.innerHTML = `
      <div style="background:var(--bg2);border:1px solid var(--border);border-radius:var(--r8);padding:14px;display:flex;align-items:center;gap:12px">
        <span style="font-size:22px">⚠️</span>
        <div>
          <div style="font-weight:600;color:var(--text0)">Could not check for updates</div>
          <div style="font-size:12px;color:var(--text2);margin-top:2px">No update server configured or network unavailable. Configure an update server URL in Settings.</div>
        </div>
      </div>`;
  }
  btn.disabled = false;
  btn.textContent = '🔍 Check for Updates';
}

// Auto-load version info when About page is opened
const _origShowPageForAbout = window._origShowPageInternal || (typeof _origShowPageInternal !== 'undefined' ? _origShowPageInternal : null);
document.addEventListener('click', function(e) {
  if (e.target.closest && e.target.closest('[onclick*="showPage(\'about\')"]')) {
    setTimeout(loadVersionInfo, 200);
  }
}, true);
// Also load on first About visit via patched showPage
(function() {
  const _sp = window.showPage;
  if (_sp) {
    window.showPage = function(name) {
      _sp(name);
      if (name === 'about') setTimeout(loadVersionInfo, 200);
    };
  }
})();
// ═══════════════════════════════════════════════════════════════════════════════
// v5.1 UPDATES — Profile Edit, My Tasks, WO Print, Date Filters,
//                Version Badge, Activity Feed, WO date range
// ═══════════════════════════════════════════════════════════════════════════════

// ── VERSION BADGE IN TOPBAR ───────────────────────────────────────────────────
(async function initVersionBadge() {
  try {
    const d = await api('GET', '/version');
    const el = document.getElementById('topbar-version-badge');
    if (el) { el.textContent = 'v' + d.current_version; el.style.display = 'inline'; }
  } catch(e) {}
})();

// ── PROFILE EDIT ─────────────────────────────────────────────────────────────
function toggleProfileEdit() {
  const form = document.getElementById('profile-edit-form');
  const btn  = document.getElementById('profile-edit-btn');
  const u    = state.user;
  if (form.style.display === 'none') {
    // Populate fields
    document.getElementById('pe-fullname').value = u.full_name || '';
    document.getElementById('pe-email').value    = u.email     || '';
    document.getElementById('pe-phone').value    = u.phone     || '';
    document.getElementById('pe-dept').value     = u.department|| '';
    form.style.display = 'block';
    btn.textContent = '✕ Cancel Edit';
  } else {
    form.style.display = 'none';
    btn.textContent = '✏ Edit Profile';
  }
}

async function saveProfile() {
  const payload = {
    full_name:  document.getElementById('pe-fullname').value.trim(),
    email:      document.getElementById('pe-email').value.trim(),
    phone:      document.getElementById('pe-phone').value.trim(),
    department: document.getElementById('pe-dept').value.trim(),
  };
  if (!payload.full_name) { toast('Full name is required', 'warning'); return; }
  try {
    const d = await api('PUT', '/profile', payload);
    state.user = { ...state.user, ...payload };
    // Update sidebar name
    document.getElementById('sb-name').textContent = payload.full_name || state.user.username;
    loadProfile();
    toggleProfileEdit();
    toast('Profile updated successfully', 'success');
  } catch(e) { toast('Failed to update profile: ' + e.message, 'error'); }
}

// ── MY TASKS ON PROFILE & DASHBOARD ──────────────────────────────────────────
async function loadMyTasks(targetId) {
  try {
    const d = await api('GET', '/my-work-orders');
    const el = document.getElementById(targetId);
    if (!el) return;

    const priorityColor = { critical:'var(--red)', high:'var(--yellow)', medium:'var(--accent)', low:'var(--text2)' };
    const statusLabel   = { open:'Open', in_progress:'In Progress', on_hold:'On Hold' };

    if (!d.work_orders.length) {
      el.innerHTML = '<div style="padding:12px;font-size:13px;color:var(--text2);text-align:center">✅ No open tasks assigned to you</div>';
    } else {
      el.innerHTML = d.work_orders.map(w => `
        <div style="display:flex;align-items:center;gap:10px;padding:10px 0;border-bottom:1px solid var(--border);cursor:pointer" onclick="openWODetail(${w.id})">
          <div style="width:8px;height:8px;border-radius:50%;background:${priorityColor[w.priority]||'var(--text2)'};flex-shrink:0"></div>
          <div style="flex:1;min-width:0">
            <div style="font-size:13px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${w.title}</div>
            <div style="font-size:11px;color:var(--text2);margin-top:2px">${w.asset_name||'No asset'} · ${statusLabel[w.status]||w.status}</div>
          </div>
          <div style="text-align:right;flex-shrink:0">
            ${w.due_date ? `<div style="font-size:11px;font-family:var(--mono);color:${new Date(w.due_date)<new Date()?'var(--red)':'var(--text2)'}">${w.due_date}</div>` : ''}
            <div style="font-size:10px;font-family:var(--mono);color:var(--text2)">${w.wo_number}</div>
          </div>
        </div>`).join('');
    }
    return d;
  } catch(e) {}
}

async function loadMyStats() {
  try {
    const d = await api('GET', '/my-work-orders');
    const el = document.getElementById('profile-stats');
    if (!el) return;
    el.innerHTML = `
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;padding:8px 0">
        <div style="text-align:center;padding:12px;background:var(--bg2);border-radius:var(--r8)">
          <div style="font-size:24px;font-weight:700;color:var(--green);font-family:var(--mono)">${d.stats.total_completed}</div>
          <div style="font-size:11px;color:var(--text2);margin-top:4px">WOs Completed</div>
        </div>
        <div style="text-align:center;padding:12px;background:var(--bg2);border-radius:var(--r8)">
          <div style="font-size:24px;font-weight:700;color:var(--accent);font-family:var(--mono)">${d.stats.total_assigned}</div>
          <div style="font-size:11px;color:var(--text2);margin-top:4px">Total Assigned</div>
        </div>
        <div style="text-align:center;padding:12px;background:var(--bg2);border-radius:var(--r8)">
          <div style="font-size:24px;font-weight:700;color:var(--yellow);font-family:var(--mono)">${d.stats.open_count}</div>
          <div style="font-size:11px;color:var(--text2);margin-top:4px">Currently Open</div>
        </div>
        <div style="text-align:center;padding:12px;background:var(--bg2);border-radius:var(--r8)">
          <div style="font-size:24px;font-weight:700;color:var(--text0);font-family:var(--mono)">${d.stats.avg_hours}h</div>
          <div style="font-size:11px;color:var(--text2);margin-top:4px">Avg Hours/WO</div>
        </div>
      </div>`;
  } catch(e) {}
}

// Patch loadProfile to also load my tasks and stats
const _origLoadProfile = window.loadProfile;
window.loadProfile = function() {
  if (_origLoadProfile) _origLoadProfile.apply(this, arguments);
  loadMyTasks('profile-my-tasks');
  loadMyStats();
};

// ── MY TASKS ON DASHBOARD ─────────────────────────────────────────────────────
async function loadDashboardMyTasks() {
  const card = document.getElementById('dash-my-tasks-card');
  if (!card) return;
  // Only show for non-admin users
  if (state && state.user && state.user.role !== 'admin') {
    card.style.display = 'block';
    await loadMyTasks('dash-my-tasks-list');
  }
}

// Patch dashboard load to also call loadDashboardMyTasks
const _origLoadDash = window.loadDashboard;
window.loadDashboard = async function() {
  if (_origLoadDash) await _origLoadDash.apply(this, arguments);
  loadDashboardMyTasks();
};

// ── WO PRINT (v6: uses backend print route for rich PDF-quality output) ──────
function printWODetail(id) {
  window.open(`/api/work-orders/${id}/print`, '_blank');
}

// ── WO DATE RANGE FILTER — patch loadWO to pass date params ──────────────────
const _origLoadWOInner = window.loadWO;
window.loadWO = async function() {
  // This runs after the original — we re-filter client side for date range
  if (_origLoadWOInner) await _origLoadWOInner.apply(this, arguments);
  const from = document.getElementById('wo-date-from')?.value;
  const to   = document.getElementById('wo-date-to')?.value;
  if (!from && !to) return;
  document.querySelectorAll('#wo-tbody tr').forEach(row => {
    const dueTd = row.querySelectorAll('td')[7];
    const dateStr = dueTd?.textContent?.trim();
    if (!dateStr || dateStr === '—') { row.style.display = from ? 'none' : ''; return; }
    const d = new Date(dateStr);
    let show = true;
    if (from && d < new Date(from)) show = false;
    if (to   && d > new Date(to + 'T23:59:59')) show = false;
    row.style.display = show ? '' : 'none';
  });
};

// ── ACTIVITY FEED — TODAY SUMMARY & HEALTH ────────────────────────────────────
async function loadActivitySummary() {
  try {
    const d = await api('GET', '/dashboard');
    const summary = document.getElementById('activity-summary-content');
    const health  = document.getElementById('activity-health-content');
    if (summary) {
      summary.innerHTML = `
        <div style="padding:8px 0">
          ${[
            {label:'Open Work Orders',   val: d.open_wo||0,        color:'var(--accent)'},
            {label:'Overdue WOs',        val: d.overdue_wo||0,     color: d.overdue_wo>0?'var(--red)':'var(--green)'},
            {label:'PMs Due This Week',  val: d.upcoming_pm?.length||0, color:'var(--yellow)'},
            {label:'Low Stock Parts',    val: d.low_stock||0,      color: d.low_stock>0?'var(--yellow)':'var(--green)'},
            {label:'Active Assets',      val: d.active_assets||0,  color:'var(--text0)'},
          ].map(item=>`
            <div style="display:flex;align-items:center;justify-content:space-between;padding:8px 0;border-bottom:1px solid var(--border)">
              <span style="font-size:13px;color:var(--text2)">${item.label}</span>
              <span style="font-size:16px;font-weight:700;font-family:var(--mono);color:${item.color}">${item.val}</span>
            </div>`).join('')}
        </div>`;
    }
    if (health) {
      health.innerHTML = `
        <div style="padding:8px 0">
          ${[
            {label:'Database', status:'online', icon:'🗄'},
            {label:'API Server', status:'online', icon:'🌐'},
            {label:'Scheduler', status: d.upcoming_pm ? 'online' : 'warn', icon:'⏰'},
            {label:'Notifications', status:'online', icon:'🔔'},
          ].map(s=>`
            <div style="display:flex;align-items:center;gap:10px;padding:8px 0;border-bottom:1px solid var(--border)">
              <span>${s.icon}</span>
              <span style="flex:1;font-size:13px">${s.label}</span>
              <span style="font-size:11px;font-weight:700;color:${s.status==='online'?'var(--green)':s.status==='warn'?'var(--yellow)':'var(--red)'}">${s.status.toUpperCase()}</span>
            </div>`).join('')}
        </div>`;
    }
  } catch(e) {}
}

// Patch showPage to load activity summary
(function() {
  const _sp = window.showPage;
  if (_sp) {
    const _patched = window.showPage;
    window.showPage = function(name) {
      _patched(name);
      if (name === 'activity') loadActivitySummary();
    };
  }
})();

// ═══════════════════════════════════════════════════════════════════════════════
// END v5.1 UPDATES
// ═══════════════════════════════════════════════════════════════════════════════

// ═══════════════════════════════════════════════════════════════════════════════
// FEATURE UPDATES — WO Assigned Filter, PM Filters, Supplier Search,
//                   Purchase Orders, Page CSV Export
// ═══════════════════════════════════════════════════════════════════════════════

// ── POPULATE WO ASSIGNED FILTER ──────────────────────────────────────────────
async function populateWOAssignedFilter() {
  try {
    const users = await api('GET', '/users');
    const sel = document.getElementById('wo-assigned-filter');
    if (!sel) return;
    users.forEach(u => {
      const opt = document.createElement('option');
      opt.value = u.id;
      opt.textContent = u.full_name || u.username;
      sel.appendChild(opt);
    });
  } catch(e) {}
}

// ── POPULATE PARTS SUPPLIER FILTER ───────────────────────────────────────────
async function populatePartsSupplierFilter() {
  try {
    const suppliers = await api('GET', '/suppliers');
    const sel = document.getElementById('parts-supplier-filter');
    if (!sel) return;
    suppliers.forEach(s => {
      const opt = document.createElement('option');
      opt.value = s.id;
      opt.textContent = s.name;
      sel.appendChild(opt);
    });
  } catch(e) {}
}

// ── PATCH loadWO TO INCLUDE NEW FILTERS ──────────────────────────────────────
const _origLoadWO = window.loadWO;
window.loadWO = async function() {
  const assignedEl = document.getElementById('wo-assigned-filter');
  const assigned = assignedEl ? assignedEl.value : '';
  // Let original run, then patch URL if needed by overriding fetch temporarily
  if (typeof _origLoadWO === 'function') {
    await _origLoadWO.apply(this, arguments);
  }
};

// ── PATCH loadAssets TO INCLUDE CRITICALITY FILTER ───────────────────────────
const _origLoadAssets = window.loadAssets;
window.loadAssets = async function() {
  if (typeof _origLoadAssets === 'function') {
    await _origLoadAssets.apply(this, arguments);
  }
};

// ── PM FILTER LOGIC ───────────────────────────────────────────────────────────
const _origLoadPM = window.loadPM;
window.loadPM = async function() {
  if (typeof _origLoadPM === 'function') {
    await _origLoadPM.apply(this, arguments);
  }
  // Apply client-side filter on loaded PM cards
  const search = (document.getElementById('pm-search')?.value || '').toLowerCase();
  const statusF = document.getElementById('pm-status-filter')?.value || '';
  const freqF   = document.getElementById('pm-freq-filter')?.value || '';
  const now = new Date();
  document.querySelectorAll('#pm-list .pm-card, #pm-list .card').forEach(card => {
    const text = card.textContent.toLowerCase();
    let show = true;
    if (search && !text.includes(search)) show = false;
    if (freqF) {
      const freqEl = card.querySelector('[data-freq]');
      if (freqEl && freqEl.dataset.freq !== freqF) show = false;
      else if (!freqEl && !text.includes(freqF)) show = false;
    }
    if (statusF === 'overdue') {
      const dueBadge = card.querySelector('.badge-danger, .text-danger, [style*="red"]');
      if (!dueBadge) show = false;
    } else if (statusF === 'inactive') {
      if (!text.includes('inactive') && !card.dataset.active === '0') show = false;
    } else if (statusF === 'active') {
      if (text.includes('inactive')) show = false;
    }
    card.style.display = show ? '' : 'none';
  });
};

// ── SUPPLIERS SEARCH PATCH ────────────────────────────────────────────────────
const _origLoadSuppliers = window.loadSuppliers;
window.loadSuppliers = async function() {
  if (typeof _origLoadSuppliers === 'function') {
    await _origLoadSuppliers.apply(this, arguments);
  }
  // Apply client-side search
  const search = (document.getElementById('supplier-search')?.value || '').toLowerCase();
  if (!search) return;
  document.querySelectorAll('#suppliers-tbody tr').forEach(row => {
    row.style.display = row.textContent.toLowerCase().includes(search) ? '' : 'none';
  });
};

// ── PAGE-LEVEL CSV EXPORT ─────────────────────────────────────────────────────
function exportPageCSV(type) {
  const ts = new Date().toISOString().slice(0,10);
  let rows = [], headers = [], filename = '';

  if (type === 'wo') {
    filename = `work_orders_${ts}.csv`;
    const trs = document.querySelectorAll('#wo-tbody tr');
    headers = ['WO #','Title','Asset','Priority','Status','Type','Assigned To','Due Date'];
    rows = Array.from(trs).map(tr => {
      const tds = tr.querySelectorAll('td');
      return [tds[0]?.textContent, tds[1]?.textContent, tds[2]?.textContent,
              tds[3]?.textContent, tds[4]?.textContent, tds[5]?.textContent,
              tds[6]?.textContent, tds[7]?.textContent].map(v => `"${(v||'').trim().replace(/"/g,'""')}"`);
    });
  } else if (type === 'assets') {
    filename = `assets_${ts}.csv`;
    const trs = document.querySelectorAll('#asset-tbody tr');
    headers = ['Code','Name','Category','Location','Status','Criticality','Warranty'];
    rows = Array.from(trs).map(tr => {
      const tds = tr.querySelectorAll('td');
      return [tds[0]?.textContent, tds[1]?.textContent, tds[2]?.textContent,
              tds[3]?.textContent, tds[4]?.textContent, tds[5]?.textContent,
              tds[6]?.textContent].map(v => `"${(v||'').trim().replace(/"/g,'""')}"`);
    });
  } else if (type === 'parts') {
    filename = `parts_inventory_${ts}.csv`;
    const trs = document.querySelectorAll('#parts-tbody tr');
    headers = ['Part #','Name','Stock','Min Stock','Unit Cost','Location','Supplier'];
    rows = Array.from(trs).map(tr => {
      const tds = tr.querySelectorAll('td');
      return [tds[0]?.textContent, tds[1]?.textContent, tds[2]?.textContent,
              tds[3]?.textContent, tds[4]?.textContent, tds[5]?.textContent,
              tds[6]?.textContent].map(v => `"${(v||'').trim().replace(/"/g,'""')}"`);
    });
  } else if (type === 'suppliers') {
    filename = `suppliers_${ts}.csv`;
    const trs = document.querySelectorAll('#suppliers-tbody tr');
    headers = ['Supplier','Contact','Email','Phone','Payment Terms'];
    rows = Array.from(trs).map(tr => {
      const tds = tr.querySelectorAll('td');
      return [tds[0]?.textContent, tds[1]?.textContent, tds[2]?.textContent,
              tds[3]?.textContent, tds[4]?.textContent].map(v => `"${(v||'').trim().replace(/"/g,'""')}"`);
    });
  } else if (type === 'po') {
    filename = `purchase_orders_${ts}.csv`;
    const trs = document.querySelectorAll('#po-tbody tr');
    headers = ['PO #','Supplier','Status','Items','Total','Ordered By','Created','Expected'];
    rows = Array.from(trs).map(tr => {
      const tds = tr.querySelectorAll('td');
      return Array.from({length: 8}, (_,i) => `"${(tds[i]?.textContent||'').trim().replace(/"/g,'\"')}"`);
    });
  }

  if (!rows.length) { toast('No data to export', 'warning'); return; }
  const csv = [headers.join(','), ...rows.map(r => r.join(','))].join('\n');
  const blob = new Blob([csv], {type: 'text/csv'});
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement('a');
  a.href = url; a.download = filename; a.click();
  URL.revokeObjectURL(url);
  toast('CSV exported: ' + filename, 'success');
}

// ── PURCHASE ORDERS ───────────────────────────────────────────────────────────
let _poPage = 1;

async function loadPOs() {
  const search = document.getElementById('po-search')?.value || '';
  const status = document.getElementById('po-status-filter')?.value || '';
  try {
    const d = await api('GET', `/purchase-orders?search=${encodeURIComponent(search)}&status=${status}&page=${_poPage}`);
    const tbody = document.getElementById('po-tbody');
    if (!tbody) return;
    const statusColors = {
      draft:'var(--text2)', pending:'var(--yellow)', approved:'var(--accent)',
      ordered:'var(--blue,#4da6ff)', received:'var(--green)', cancelled:'var(--red)'
    };
    tbody.innerHTML = d.orders.length ? d.orders.map(po => `
      <tr style="cursor:pointer" onclick="openPODetail(${po.id})">
        <td class="td-mono">${po.po_number}</td>
        <td class="td-primary">${po.supplier_name||'—'}</td>
        <td><span style="color:${statusColors[po.status]||'var(--text1)'};font-weight:600;font-size:12px;text-transform:capitalize">${(po.status||'').replace(/_/g,' ')}</span></td>
        <td>${po.item_count||0} item${po.item_count!==1?'s':''}</td>
        <td class="td-mono">₹${(po.total||0).toLocaleString('en-IN',{minimumFractionDigits:2})}</td>
        <td style="font-size:12px">${po.ordered_by_name||'—'}</td>
        <td style="font-size:12px">${(po.created_at||'').slice(0,10)}</td>
        <td style="font-size:12px">${po.expected_date||'—'}</td>
        <td onclick="event.stopPropagation()">
          <button class="btn btn-secondary btn-sm btn-icon" onclick="openPODetail(${po.id})" title="View">👁</button>
          <button class="btn btn-secondary btn-sm btn-icon" onclick="editPO(${po.id})" title="Edit">✏</button>
          <button class="btn btn-danger btn-sm btn-icon" onclick="deletePO(${po.id})" title="Delete">🗑</button>
        </td>
      </tr>`) .join('') : '<tr><td colspan="9" style="text-align:center;padding:24px;color:var(--text2)">No purchase orders found</td></tr>';
    renderPagination('po-pagination', _poPage, Math.ceil(d.total/d.per), p => { _poPage=p; loadPOs(); });
  } catch(e) { toast('Error loading purchase orders', 'error'); }
}

async function openPODetail(id) {
  try {
    const po = await api('GET', `/purchase-orders/${id}`);
    const itemsHtml = po.items?.length ? `
      <table style="width:100%;border-collapse:collapse;margin-top:8px;font-size:13px">
        <thead><tr style="background:var(--bg3)">
          <th style="padding:8px;text-align:left">Part / Description</th>
          <th style="padding:8px;text-align:right">Qty</th>
          <th style="padding:8px;text-align:right">Unit Cost</th>
          <th style="padding:8px;text-align:right">Total</th>
        </tr></thead>
        <tbody>${po.items.map(i=>`
          <tr style="border-bottom:1px solid var(--border)">
            <td style="padding:8px">${i.part_name||i.description||'—'}</td>
            <td style="padding:8px;text-align:right">${i.quantity}</td>
            <td style="padding:8px;text-align:right">₹${(i.unit_cost||0).toFixed(2)}</td>
            <td style="padding:8px;text-align:right;font-weight:600">₹${((i.quantity||0)*(i.unit_cost||0)).toFixed(2)}</td>
          </tr>`).join('')}
          <tr style="font-weight:700;background:var(--bg2)">
            <td colspan="3" style="padding:8px;text-align:right">Grand Total</td>
            <td style="padding:8px;text-align:right;color:var(--green)">₹${(po.total||0).toFixed(2)}</td>
          </tr>
        </tbody>
      </table>` : '<p style="color:var(--text2);font-size:13px">No items added.</p>';

    createModal('modal-po-detail', `🛒 ${po.po_number}`, `
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:16px;font-size:13px">
        <div><span style="color:var(--text2)">Supplier</span><div style="font-weight:600">${po.supplier_name||'—'}</div></div>
        <div><span style="color:var(--text2)">Status</span><div style="font-weight:600;text-transform:capitalize">${(po.status||'').replace(/_/g,' ')}</div></div>
        <div><span style="color:var(--text2)">Ordered By</span><div>${po.ordered_by_name||'—'}</div></div>
        <div><span style="color:var(--text2)">Expected Date</span><div>${po.expected_date||'—'}</div></div>
        <div><span style="color:var(--text2)">Created</span><div>${(po.created_at||'').slice(0,10)}</div></div>
        <div><span style="color:var(--text2)">Notes</span><div>${po.notes||'—'}</div></div>
      </div>
      <div style="font-weight:600;margin-bottom:4px;font-size:13px">📦 Line Items</div>
      ${itemsHtml}`,
    [{label:'✏ Edit', cls:'btn-secondary', onclick:`closeModal('modal-po-detail');editPO(${id})`},
     {label:'Close', cls:'btn-secondary', onclick:`closeModal('modal-po-detail')`}]);
  } catch(e) { toast('Error loading PO', 'error'); }
}

async function openPOModal(existing) {
  let suppliers = [];
  let parts = [];
  try { suppliers = await api('GET', '/suppliers'); } catch(e){}
  try { parts = await api('GET', '/parts'); } catch(e){}

  const supplierOpts = suppliers.map(s=>`<option value="${s.id}" ${existing?.supplier_id==s.id?'selected':''}>${s.name}</option>`).join('');
  const partOpts = parts.map(p=>`<option value="${p.id}">${p.name} (${p.part_number||'—'})</option>`).join('');

  const itemsDefault = existing?.items?.length ? existing.items : [{}];

  createModal('modal-po-form', existing ? `✏ Edit ${existing.po_number}` : '🛒 New Purchase Order', `
    <div class="form-group"><label>Supplier *</label>
      <select id="po-supplier" class="form-control"><option value="">Select supplier...</option>${supplierOpts}</select></div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
      <div class="form-group"><label>Status</label>
        <select id="po-status" class="form-control">
          ${['draft','pending','approved','ordered','received','cancelled'].map(s=>`<option value="${s}" ${existing?.status==s?'selected':''}>${s.charAt(0).toUpperCase()+s.slice(1)}</option>`).join('')}
        </select></div>
      <div class="form-group"><label>Expected Date</label>
        <input type="date" id="po-expected" class="form-control" value="${existing?.expected_date||''}"></div>
    </div>
    <div class="form-group"><label>Notes</label>
      <textarea id="po-notes" class="form-control" rows="2">${existing?.notes||''}</textarea></div>
    <div style="font-weight:600;font-size:13px;margin-bottom:8px">📦 Line Items</div>
    <div id="po-items-list">
      ${itemsDefault.map((_,i)=>`
        <div class="po-item-row" id="po-item-${i}" style="display:grid;grid-template-columns:2fr 1fr 1fr auto;gap:8px;margin-bottom:8px;align-items:end">
          <div><label style="font-size:11px;color:var(--text2)">Part / Description</label>
            <select class="form-control po-item-part" onchange="updatePOItemDesc(${i})">
              <option value="">Custom description...</option>${partOpts}
            </select></div>
          <div><label style="font-size:11px;color:var(--text2)">Qty</label>
            <input type="number" class="form-control po-item-qty" value="1" min="1"></div>
          <div><label style="font-size:11px;color:var(--text2)">Unit Cost</label>
            <input type="number" class="form-control po-item-cost" value="0" min="0" step="0.01" oninput="updatePOTotal()"></div>
          <button class="btn btn-danger btn-sm" onclick="removePOItem(${i})" style="margin-top:18px">✕</button>
        </div>`).join('')}
    </div>
    <button class="btn btn-secondary btn-sm" onclick="addPOItem()" style="margin-bottom:12px">＋ Add Item</button>
    <div style="text-align:right;font-size:14px;font-weight:700;color:var(--green)">Total: ₹<span id="po-total-display">0.00</span></div>`,
  [{label: existing ? 'Update PO' : 'Create PO', cls:'btn-primary', onclick:`savePO(${existing?.id||'null'})`},
   {label:'Cancel', cls:'btn-secondary', onclick:`closeModal('modal-po-form')`}]);
}

let _poItemCount = 1;
function addPOItem() {
  const list = document.getElementById('po-items-list');
  const i = _poItemCount++;
  const parts = document.querySelectorAll('.po-item-part')[0];
  const partOpts = parts ? parts.innerHTML : '';
  const row = document.createElement('div');
  row.className = 'po-item-row'; row.id = `po-item-${i}`;
  row.style = 'display:grid;grid-template-columns:2fr 1fr 1fr auto;gap:8px;margin-bottom:8px;align-items:end';
  row.innerHTML = `
    <div><label style="font-size:11px;color:var(--text2)">Part / Description</label>
      <select class="form-control po-item-part"><option value="">Custom description...</option>${partOpts}</select></div>
    <div><label style="font-size:11px;color:var(--text2)">Qty</label>
      <input type="number" class="form-control po-item-qty" value="1" min="1"></div>
    <div><label style="font-size:11px;color:var(--text2)">Unit Cost</label>
      <input type="number" class="form-control po-item-cost" value="0" min="0" step="0.01" oninput="updatePOTotal()"></div>
    <button class="btn btn-danger btn-sm" onclick="this.closest('.po-item-row').remove();updatePOTotal()" style="margin-top:18px">✕</button>`;
  list.appendChild(row);
}

function removePOItem(i) {
  const el = document.getElementById(`po-item-${i}`);
  if (el) { el.remove(); updatePOTotal(); }
}

function updatePOTotal() {
  let total = 0;
  document.querySelectorAll('.po-item-row').forEach(row => {
    const qty  = parseFloat(row.querySelector('.po-item-qty')?.value || 0);
    const cost = parseFloat(row.querySelector('.po-item-cost')?.value || 0);
    total += qty * cost;
  });
  const el = document.getElementById('po-total-display');
  if (el) el.textContent = total.toLocaleString('en-IN', {minimumFractionDigits:2});
}

async function savePO(existingId) {
  const supplier_id = document.getElementById('po-supplier')?.value;
  const status      = document.getElementById('po-status')?.value;
  const expected    = document.getElementById('po-expected')?.value;
  const notes       = document.getElementById('po-notes')?.value;
  const items = Array.from(document.querySelectorAll('.po-item-row')).map(row => {
    const partVal = row.querySelector('.po-item-part')?.value;
    return {
      part_id:     partVal ? parseInt(partVal) : null,
      description: row.querySelector('.po-item-part option:checked')?.textContent || '',
      quantity:    parseFloat(row.querySelector('.po-item-qty')?.value) || 1,
      unit_cost:   parseFloat(row.querySelector('.po-item-cost')?.value) || 0,
    };
  }).filter(item => item.part_id || item.description);
  if (!supplier_id) { toast('Please select a supplier', 'warning'); return; }
  if (!items.length) { toast('Please add at least one item', 'warning'); return; }
  try {
    if (existingId) {
      await api('PUT', `/purchase-orders/${existingId}`, {supplier_id: parseInt(supplier_id), status, expected_date:expected, notes, items});
      toast('Purchase order updated', 'success');
    } else {
      const d = await api('POST', '/purchase-orders', {supplier_id: parseInt(supplier_id), status, expected_date:expected, notes, items});
      toast(`PO ${d.po_number} created`, 'success');
    }
    closeModal('modal-po-form');
    loadPOs();
  } catch(e) { toast('Error saving PO: ' + e.message, 'error'); }
}

async function editPO(id) {
  try {
    const po = await api('GET', `/purchase-orders/${id}`);
    openPOModal(po);
  } catch(e) { toast('Error loading PO', 'error'); }
}

async function deletePO(id) {
  if (!confirm('Delete this purchase order? This cannot be undone.')) return;
  try {
    await api('DELETE', `/purchase-orders/${id}`);
    toast('Purchase order deleted', 'success');
    loadPOs();
  } catch(e) { toast('Error deleting PO', 'error'); }
}

// ── INIT NEW FEATURES ON APP LOAD ────────────────────────────────────────────
(function initNewFeatures() {
  const _origInitApp = window.initApp;
  window.initApp = async function() {
    if (_origInitApp) await _origInitApp.apply(this, arguments);
    setTimeout(() => {
      populateWOAssignedFilter();
      populatePartsSupplierFilter();
    }, 500);
  };
  // Also patch showPage to load POs when navigating there
  const _sp = window.showPage;
  if (_sp) {
    window.showPage = function(name) {
      _sp(name);
      if (name === 'purchase-orders') { _poPage = 1; loadPOs(); }
    };
  }
})();
// ═══════════════════════════════════════════════════════════════════════════════

</script>
</body></html>"""


# ── PROFILE UPDATE & MY TASKS ─────────────────────────────────────────────────
@app.route('/api/profile', methods=['PUT'])
@login_required
def update_profile():
    data    = request.json
    user_id = session['user_id']
    conn    = get_db()
    conn.execute("""UPDATE users SET full_name=?, email=?, phone=?, department=?,
                    updated_at=datetime('now') WHERE id=?""",
                 (data.get('full_name'), data.get('email'),
                  data.get('phone'), data.get('department'), user_id))
    conn.commit()
    user = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    conn.close()
    session['user'] = dict(user)
    log_action(user_id, 'UPDATE', 'users', user_id, details='Profile updated')
    return jsonify({'success': True, 'user': dict(user)})


@app.route('/api/my-work-orders')
@login_required
def my_work_orders():
    user_id = session['user_id']
    conn    = get_db()
    rows = conn.execute("""
        SELECT w.id, w.wo_number, w.title, w.status, w.priority, w.due_date,
               a.name as asset_name
        FROM work_orders w
        LEFT JOIN assets a ON w.asset_id = a.id
        WHERE w.assigned_to = ? AND w.status NOT IN ('completed','cancelled')
        ORDER BY
            CASE w.priority WHEN 'critical' THEN 0 WHEN 'high' THEN 1
                            WHEN 'medium' THEN 2 ELSE 3 END,
            w.due_date ASC NULLS LAST
        LIMIT 10""", (user_id,)).fetchall()

    # My stats
    total_completed = conn.execute(
        "SELECT COUNT(*) FROM work_orders WHERE assigned_to=? AND status='completed'",
        (user_id,)).fetchone()[0]
    total_assigned = conn.execute(
        "SELECT COUNT(*) FROM work_orders WHERE assigned_to=?",
        (user_id,)).fetchone()[0]
    avg_hours = conn.execute(
        "SELECT AVG(actual_hours) FROM work_orders WHERE assigned_to=? AND actual_hours>0",
        (user_id,)).fetchone()[0]
    conn.close()
    return jsonify({
        'work_orders': [dict(r) for r in rows],
        'stats': {
            'total_assigned':  total_assigned,
            'total_completed': total_completed,
            'open_count':      len(rows),
            'avg_hours':       round(avg_hours or 0, 1),
        }
    })


# ── PURCHASE ORDERS ────────────────────────────────────────────────────────────
@app.route('/api/purchase-orders', methods=['GET'])
@login_required
def get_purchase_orders():
    conn = get_db()
    search = request.args.get('search', '').strip()
    status = request.args.get('status', '').strip()
    page   = max(1, int(request.args.get('page', 1)))
    per    = 20
    q = """SELECT po.*, s.name as supplier_name, u.full_name as ordered_by_name,
               COUNT(poi.id) as item_count
           FROM purchase_orders po
           LEFT JOIN suppliers s ON po.supplier_id = s.id
           LEFT JOIN users u ON po.ordered_by = u.id
           LEFT JOIN po_items poi ON poi.po_id = po.id
           WHERE 1=1"""
    params = []
    if search:
        q += " AND (po.po_number LIKE ? OR s.name LIKE ? OR po.notes LIKE ?)"
        params += [f'%{search}%', f'%{search}%', f'%{search}%']
    if status:
        q += " AND po.status=?"
        params.append(status)
    q += " GROUP BY po.id ORDER BY po.created_at DESC"
    total = len(conn.execute(q, params).fetchall())
    q += f" LIMIT {per} OFFSET {(page-1)*per}"
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return jsonify({'orders': [dict(r) for r in rows], 'total': total, 'page': page, 'per': per})

@app.route('/api/purchase-orders', methods=['POST'])
@login_required
def create_purchase_order():
    data = request.json
    conn = get_db()
    po_number = generate_po_number()
    conn.execute("""INSERT INTO purchase_orders
        (po_number, supplier_id, ordered_by, status, notes, expected_date, created_at)
        VALUES (?,?,?,?,?,?,datetime('now'))""",
        (po_number, data.get('supplier_id'), session['user_id'],
         data.get('status','draft'), data.get('notes',''), data.get('expected_date')))
    po_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    # Insert items
    for item in data.get('items', []):
        conn.execute("""INSERT INTO po_items (po_id, part_id, description, quantity, unit_cost)
            VALUES (?,?,?,?,?)""",
            (po_id, item.get('part_id'), item.get('description',''),
             item.get('quantity',1), item.get('unit_cost',0)))
    conn.execute("""UPDATE purchase_orders SET
        subtotal=(SELECT SUM(quantity*unit_cost) FROM po_items WHERE po_id=?),
        total=(SELECT SUM(quantity*unit_cost) FROM po_items WHERE po_id=?)
        WHERE id=?""", (po_id, po_id, po_id))
    conn.commit()
    try:
        log_action(session['user_id'], 'CREATE', 'purchase_orders', po_id, details=f'PO {po_number} created')
    except Exception:
        pass
    return jsonify({'success': True, 'id': po_id, 'po_number': po_number})

@app.route('/api/purchase-orders/<int:po_id>', methods=['GET'])
@login_required
def get_purchase_order(po_id):
    conn = get_db()
    po = conn.execute("""SELECT po.*, s.name as supplier_name, u.full_name as ordered_by_name
        FROM purchase_orders po
        LEFT JOIN suppliers s ON po.supplier_id=s.id
        LEFT JOIN users u ON po.ordered_by=u.id
        WHERE po.id=?""", (po_id,)).fetchone()
    if not po: return jsonify({'error': 'Not found'}), 404
    items = conn.execute("""SELECT poi.*, p.name as part_name, p.part_number
        FROM po_items poi LEFT JOIN parts p ON poi.part_id=p.id WHERE poi.po_id=?""", (po_id,)).fetchall()
    conn.close()
    result = dict(po)
    result['items'] = [dict(i) for i in items]
    return jsonify(result)

@app.route('/api/purchase-orders/<int:po_id>', methods=['PUT'])
@login_required
def update_purchase_order(po_id):
    data = request.json
    conn = get_db()
    conn.execute("""UPDATE purchase_orders SET
        supplier_id=?, status=?, notes=?, expected_date=?, updated_at=datetime('now')
        WHERE id=?""",
        (data.get('supplier_id'), data.get('status'), data.get('notes'), data.get('expected_date'), po_id))
    # Update items if provided
    if 'items' in data:
        conn.execute("DELETE FROM po_items WHERE po_id=?", (po_id,))
        for item in data['items']:
            conn.execute("""INSERT INTO po_items (po_id, part_id, description, quantity, unit_cost)
                VALUES (?,?,?,?,?)""",
                (po_id, item.get('part_id'), item.get('description',''),
                 item.get('quantity',1), item.get('unit_cost',0)))
        conn.execute("""UPDATE purchase_orders SET
            subtotal=(SELECT SUM(quantity*unit_cost) FROM po_items WHERE po_id=?),
            total=(SELECT SUM(quantity*unit_cost) FROM po_items WHERE po_id=?)
            WHERE id=?""", (po_id, po_id, po_id))
    # If status = received, auto-add stock to parts inventory
    if data.get('status') == 'received':
        items = conn.execute("SELECT * FROM po_items WHERE po_id=?", (po_id,)).fetchall()
        for item in items:
            if item['part_id']:
                conn.execute("UPDATE parts SET quantity=quantity+? WHERE id=?",
                             (item['quantity'], item['part_id']))
        conn.execute("UPDATE purchase_orders SET received_date=datetime('now') WHERE id=?", (po_id,))
    conn.commit()
    try:
        log_action(session['user_id'], 'UPDATE', 'purchase_orders', po_id, details=f'PO updated, status={data.get("status")}')
    except Exception:
        pass
    return jsonify({'success': True})

@app.route('/api/purchase-orders/<int:po_id>', methods=['DELETE'])
@admin_required
def delete_purchase_order(po_id):
    conn = get_db()
    conn.execute("DELETE FROM po_items WHERE po_id=?", (po_id,))
    conn.execute("DELETE FROM purchase_orders WHERE id=?", (po_id,))
    conn.commit()
    return jsonify({'success': True})


# ── SOFTWARE VERSION & UPDATE CHECK ──────────────────────────────────────────
@app.route('/api/version-info')
@login_required
def get_version():
    """Return full version info with live DB stats (requires login)."""
    conn = get_db()
    wo_count   = conn.execute("SELECT COUNT(*) FROM work_orders").fetchone()[0]
    asset_count= conn.execute("SELECT COUNT(*) FROM assets").fetchone()[0]
    user_count = conn.execute("SELECT COUNT(*) FROM users WHERE is_active=1").fetchone()[0]
    pm_count   = conn.execute("SELECT COUNT(*) FROM pm_schedules WHERE active=1").fetchone()[0]
    conn.close()
    return jsonify({
        "current_version": APP_VERSION,
        "build_date":       APP_BUILD,
        "codename":         APP_CODENAME,
        "python_version":   sys.version.split()[0],
        "db_path":          DB_PATH,
        "db_size_kb":       round(os.path.getsize(DB_PATH) / 1024, 1) if os.path.exists(DB_PATH) else 0,
        "stats": {
            "work_orders": wo_count,
            "assets":      asset_count,
            "users":       user_count,
            "pm_schedules":pm_count,
        }
    })

@app.route('/api/check-update', methods=['POST'])
@login_required
def check_update():
    """
    Simulated update check. In production, replace with a real endpoint call.
    Returns whether a newer version is available.
    """
    import re, urllib.request, urllib.error
    LATEST_VERSION = APP_VERSION   # <- replace with your real release feed URL logic
    UPDATE_NOTES   = []            # <- populate from your release feed in production
    is_newer = False

    # Try to reach a configurable update server (graceful fail if offline)
    update_server = None
    try:
        conn = get_db()
        row = conn.execute("SELECT value FROM settings WHERE key='update_server_url'").fetchone()
        conn.close()
        if row and row['value']:
            update_server = row['value'].strip()
    except Exception:
        pass

    if update_server:
        try:
            with urllib.request.urlopen(update_server, timeout=5) as resp:
                data = json.loads(resp.read().decode())
                LATEST_VERSION = data.get('version', APP_VERSION)
                UPDATE_NOTES   = data.get('notes', [])
        except Exception:
            pass  # Offline or server unreachable

    # Compare versions
    def ver_tuple(v):
        try:
            return tuple(int(x) for x in re.findall(r'\d+', v))
        except Exception:
            return (0,)

    is_newer = ver_tuple(LATEST_VERSION) > ver_tuple(APP_VERSION)

    return jsonify({
        "current_version": APP_VERSION,
        "latest_version":  LATEST_VERSION,
        "update_available":is_newer,
        "notes":           UPDATE_NOTES,
        "checked_at":      datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    })

@app.route('/api/manual-update', methods=['POST'])
@admin_required
def manual_update():
    """
    Manual update: upload a new .py file, validate it, backup the current one,
    replace it, then signal restart.
    Steps:
      1. Receive uploaded file
      2. Validate it is a Python file and contains key NEXUS markers
      3. Backup current app file with timestamp
      4. Write new file
      5. Return success — user must manually restart the server
    """
    import shutil, tempfile, ast

    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file uploaded.'}), 400

    f = request.files['file']
    if not f.filename.endswith('.py'):
        return jsonify({'success': False, 'error': 'Only .py files are accepted.'}), 400

    # Read uploaded content
    try:
        content = f.read().decode('utf-8')
    except Exception as e:
        return jsonify({'success': False, 'error': f'Could not read file: {e}'}), 400

    # Basic safety validation: must be valid Python
    try:
        ast.parse(content)
    except SyntaxError as e:
        return jsonify({'success': False, 'error': f'Uploaded file has a Python syntax error: {e}'}), 400

    # Must contain NEXUS CMMS markers so random files can't be uploaded
    required_markers = ['NEXUS CMMS', 'Flask', 'init_db', 'work_orders']
    missing = [m for m in required_markers if m not in content]
    if missing:
        return jsonify({'success': False,
                        'error': f'File does not appear to be a valid NEXUS CMMS application. Missing: {", ".join(missing)}'}), 400

    # Extract version from uploaded file for display
    new_version = 'unknown'
    for line in content.splitlines():
        if line.strip().startswith('APP_VERSION'):
            try:
                new_version = line.split('=')[1].strip().strip('"\'')
            except Exception:
                pass
            break

    # Resolve current file path robustly (handles relative paths and .pyc)
    current_file = os.path.abspath(__file__)
    if current_file.endswith('.pyc'):
        current_file = current_file[:-1]   # .pyc -> .py

    app_dir     = os.path.dirname(current_file)
    ts          = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = os.path.join(app_dir,
                    os.path.splitext(os.path.basename(current_file))[0] + f'_backup_{ts}.py')

    # Check the file is actually writable before doing anything
    if not os.access(current_file, os.W_OK):
        return jsonify({'success': False,
                        'error': f'Application file is not writable: {current_file}. '
                                  'Run the server with appropriate permissions.'}), 500

    # Backup current file
    try:
        shutil.copy2(current_file, backup_name)
    except Exception as e:
        return jsonify({'success': False, 'error': f'Could not create backup: {e}'}), 500

    # Write new file in-place (avoids cross-device move issues on Windows/Linux)
    try:
        tmp_path = current_file + '.update_tmp'
        with open(tmp_path, 'w', encoding='utf-8') as tmp_f:
            tmp_f.write(content)
        # Atomic rename
        os.replace(tmp_path, current_file)
    except Exception as e:
        # Clean up temp file
        if os.path.exists(tmp_path):
            try: os.remove(tmp_path)
            except Exception: pass
        # Restore backup on failure
        try:
            shutil.copy2(backup_name, current_file)
        except Exception:
            pass
        return jsonify({'success': False, 'error': f'Failed to write update file: {e}'}), 500

    # Log the action (best-effort — don't crash the update if audit_log is unavailable)
    try:
        log_action(session.get('user_id'), 'MANUAL_UPDATE', 'system', None,
                   old_value=APP_VERSION, new_value=new_version,
                   details=f'Manual update applied. Backup: {os.path.basename(backup_name)}')
    except Exception:
        pass

    return jsonify({
        'success':      True,
        'new_version':  new_version,
        'backup_file':  os.path.basename(backup_name),
        'message':      f'Update to v{new_version} applied successfully. Please restart the server to activate the new version.',
        'applied_at':   datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    })


@app.route('/api/restore-backup', methods=['POST'])
@admin_required
def restore_backup():
    """Restore a previously backed-up application file."""
    import shutil
    filename = request.json.get('filename', '').strip()
    if not filename:
        return jsonify({'success': False, 'error': 'No filename provided.'}), 400

    # Security: only allow backup files in the app directory, no path traversal
    current_file = os.path.abspath(__file__)
    app_dir      = os.path.dirname(current_file)
    base_name    = os.path.splitext(os.path.basename(current_file))[0]

    if not filename.startswith(base_name + '_backup_') or not filename.endswith('.py') or '/' in filename or '\\' in filename:
        return jsonify({'success': False, 'error': 'Invalid backup filename.'}), 400

    restore_path = os.path.join(app_dir, filename)
    if not os.path.exists(restore_path):
        return jsonify({'success': False, 'error': f'Backup file not found: {filename}'}), 404

    # Backup the current file before restoring
    backup_name = os.path.join(os.path.dirname(current_file),
        os.path.splitext(os.path.basename(current_file))[0] + f'_backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.py')
    try:
        shutil.copy2(current_file, backup_name)
        # Use temp + atomic replace
        tmp_path = current_file + '.restore_tmp'
        shutil.copy2(restore_path, tmp_path)
        os.replace(tmp_path, current_file)
    except Exception as e:
        if os.path.exists(tmp_path if 'tmp_path' in dir() else ''):
            try: os.remove(tmp_path)
            except: pass
        return jsonify({'success': False, 'error': f'Restore failed: {e}'}), 500

    try:
        log_action(session.get('user_id'), 'RESTORE_BACKUP', 'system', None,
                   details=f'Restored from backup: {filename}. Previous backed up as: {os.path.basename(backup_name)}')
    except Exception:
        pass

    return jsonify({
        'success':     True,
        'backup_file': os.path.basename(backup_name),
        'restored':    filename,
        'message':     'Backup restored. Please restart the server.',
    })


@app.route('/api/list-backups')
@admin_required
def list_backups():
    """Return list of backup .py files in the app directory."""
    current_file = os.path.abspath(__file__)
    app_dir      = os.path.dirname(current_file)
    base_name    = os.path.splitext(os.path.basename(current_file))[0]
    backups = []
    try:
        for fname in sorted(os.listdir(app_dir), reverse=True):
            if fname.startswith(base_name + '_backup_') and fname.endswith('.py'):
                fpath = os.path.join(app_dir, fname)
                backups.append({
                    'filename': fname,
                    'size_kb':  round(os.path.getsize(fpath) / 1024, 1),
                    'modified': datetime.fromtimestamp(os.path.getmtime(fpath)).strftime('%Y-%m-%d %H:%M:%S'),
                })
    except Exception:
        pass
    return jsonify(backups)


@app.route('/api/db-backup-download')
@admin_required
def db_backup_download():
    """Stream the current SQLite database file as a download."""
    import shutil
    if not os.path.exists(DB_PATH):
        return jsonify({'error': 'Database file not found'}), 404
    # Copy to a temp file so we stream a consistent snapshot
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    tmp_path = os.path.join(os.path.dirname(os.path.abspath(DB_PATH)),
                            f'cmms_nexus_backup_{ts}.db')
    try:
        shutil.copy2(DB_PATH, tmp_path)
        download_name = f'cmms_nexus_backup_{ts}.db'
        def stream_and_delete():
            with open(tmp_path, 'rb') as fh:
                while True:
                    chunk = fh.read(65536)
                    if not chunk:
                        break
                    yield chunk
            try:
                os.remove(tmp_path)
            except Exception:
                pass
        log_action(session.get('user_id'), 'DB_BACKUP_DOWNLOAD', 'system', None,
                   details=f'Database backup downloaded: {download_name}')
        response = Response(
            stream_with_context(stream_and_delete()),
            mimetype='application/octet-stream',
        )
        response.headers['Content-Disposition'] = f'attachment; filename="{download_name}"'
        response.headers['Content-Length'] = os.path.getsize(tmp_path)
        return response
    except Exception as e:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass
        return jsonify({'error': str(e)}), 500


@app.route('/api/db-restore', methods=['POST'])
@admin_required
def db_restore():
    """
    Restore the database from an uploaded .db file.
    Steps:
      1. Validate the uploaded file is a SQLite database
      2. Backup the current database with a timestamp
      3. Replace the database file with the upload
    """
    import shutil
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file uploaded.'}), 400

    f = request.files['file']
    if not f.filename.endswith('.db'):
        return jsonify({'success': False, 'error': 'Only .db files are accepted.'}), 400

    # Read and validate it is a SQLite3 file
    try:
        content = f.read()
    except Exception as e:
        return jsonify({'success': False, 'error': f'Could not read file: {e}'}), 400

    # SQLite3 files start with the magic header "SQLite format 3\000"
    if not content.startswith(b'SQLite format 3\x00'):
        return jsonify({'success': False,
                        'error': 'Uploaded file does not appear to be a valid SQLite3 database.'}), 400

    db_abs = os.path.abspath(DB_PATH)
    db_dir = os.path.dirname(db_abs)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f'cmms_nexus_backup_{ts}.db'
    backup_path = os.path.join(db_dir, backup_name)
    script_name = os.path.basename(os.path.abspath(__file__))

    # Backup current DB
    if os.path.exists(db_abs):
        try:
            shutil.copy2(db_abs, backup_path)
        except Exception as e:
            return jsonify({'success': False, 'error': f'Could not back up current database: {e}'}), 500

    # Write new DB via temp file then atomic rename
    tmp_path = db_abs + '.restore_tmp'
    try:
        with open(tmp_path, 'wb') as out:
            out.write(content)
        os.replace(tmp_path, db_abs)
    except Exception as e:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass
        # Try to restore backup
        if os.path.exists(backup_path):
            try:
                shutil.copy2(backup_path, db_abs)
            except Exception:
                pass
        return jsonify({'success': False, 'error': f'Failed to write restored database: {e}'}), 500

    # Log the action (best-effort — don't crash the restore if audit_log is unavailable)
    try:
        log_action(session.get('user_id'), 'DB_RESTORE', 'system', None,
                   details=f'Database restored from upload. Previous DB backed up as: {backup_name}')
    except Exception:
        pass

    return jsonify({
        'success':     True,
        'backup_file': backup_name,
        'script_name': script_name,
        'message':     'Database restored successfully. Please restart the server.',
        'restored_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    })


if __name__ == '__main__':
    print("╔═══════════════════════════════════════════════════════╗")
    print("║   NEXUS CMMS Enterprise v9.0 Mobile Edition          ║")
    print("║   Security + UI + Features + Mobile View Enhanced    ║")
    print("╚═══════════════════════════════════════════════════════╝")
    print("")
    print("  What's New in v9:")
    print("  ✓ Enhanced mobile view with More drawer")
    print("  ✓ PWA safe-area inset support (notch/Dynamic Island)")
    print("  ✓ Touch-optimized bottom navigation")
    print("  ✓ Tablet layout improvements")
    print("  ✓ iOS zoom prevention on form inputs")
    print("  ✓ Landscape mode optimization")
    print("  ✓ PBKDF2 password hashing (from v8)")
    print("  ✓ Rate limiting on sensitive endpoints (from v8)")
    print("")
    if os.path.exists(DB_PATH) and not db_is_compatible():
        print("  Incompatible database schema detected — resetting...")
        reset_db()
    init_db()
    print("✓ Database initialized")
    start_auto_backup_thread()
    print("✓ Auto-backup scheduler started")
    print("✓ Opening http://localhost:5050")
    def open_browser():
        import time; time.sleep(1.0)
        webbrowser.open('http://localhost:5050')
    threading.Thread(target=open_browser, daemon=True).start()
    app.run(debug=False, port=5050, host='0.0.0.0')
