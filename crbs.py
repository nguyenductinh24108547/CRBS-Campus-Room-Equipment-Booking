"""CRBS educational prototype. Python 3.10+, SQLite, standard library only.
External SSO/Inventory/Email/SMS are simulated; this is not production software.
"""
import sqlite3
from datetime import datetime, timedelta, date
from typing import Optional

class CRBSError(ValueError):
    pass

ROLES = {"Student", "Lecturer", "Facility Staff", "System Admin"}
STATUSES = {"Pending", "Approved", "Rejected", "Cancelled"}
CONDITIONS = {"Good", "Damaged", "Missing"}

class CRBS:
    def __init__(self, db_path=":memory:", student_weekly_quota=None, notification_available=True):
        self.db = sqlite3.connect(db_path)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.student_weekly_quota = student_weekly_quota
        self.notification_available = notification_available
        self._schema()

    def _schema(self):
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS users(
          id INTEGER PRIMARY KEY, display_name TEXT NOT NULL,
          role TEXT NOT NULL CHECK(role IN ('Student','Lecturer','Facility Staff','System Admin')),
          active INTEGER NOT NULL DEFAULT 1,
          email TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS resources(
          id INTEGER PRIMARY KEY, name TEXT NOT NULL,
          kind TEXT NOT NULL CHECK(kind IN ('Room','Seminar Room','Equipment')),
          capacity INTEGER NOT NULL DEFAULT 1 CHECK(capacity >= 1),
          restricted INTEGER NOT NULL DEFAULT 0,
          allowed_roles TEXT NOT NULL DEFAULT 'Lecturer,Facility Staff,System Admin',
          maintenance INTEGER NOT NULL DEFAULT 0,
          active INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS bookings(
          id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
          resource_id INTEGER NOT NULL REFERENCES resources(id),
          start_time TEXT NOT NULL, end_time TEXT NOT NULL,
          purpose TEXT NOT NULL, attendees INTEGER NOT NULL,
          support_notes TEXT NOT NULL DEFAULT '',
          status TEXT NOT NULL CHECK(status IN ('Pending','Approved','Rejected','Cancelled')),
          decision_reason TEXT NOT NULL DEFAULT '',
          created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_booking_resource_time ON bookings(resource_id,start_time,end_time,status);
        CREATE TABLE IF NOT EXISTS booking_items(
          id INTEGER PRIMARY KEY, booking_id INTEGER NOT NULL REFERENCES bookings(id),
          resource_id INTEGER NOT NULL REFERENCES resources(id),
          item_role TEXT NOT NULL CHECK(item_role IN ('PRIMARY','BUNDLED_EQUIPMENT')),
          UNIQUE(booking_id,resource_id)
        );
        CREATE TABLE IF NOT EXISTS equipment_transactions(
          id INTEGER PRIMARY KEY, booking_id INTEGER NOT NULL REFERENCES bookings(id),
          resource_id INTEGER NOT NULL REFERENCES resources(id),
          checkout_staff_id INTEGER NOT NULL REFERENCES users(id),
          checkout_at TEXT NOT NULL,
          checkin_staff_id INTEGER REFERENCES users(id),
          checkin_at TEXT,
          condition TEXT,
          notes TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS maintenance_incidents(
          id INTEGER PRIMARY KEY, resource_id INTEGER NOT NULL REFERENCES resources(id),
          opened_by INTEGER NOT NULL REFERENCES users(id), description TEXT NOT NULL,
          status TEXT NOT NULL CHECK(status IN ('Open','Closed')),
          opened_at TEXT NOT NULL, closed_by INTEGER REFERENCES users(id),
          closed_at TEXT, resolution TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS audit_log(
          id INTEGER PRIMARY KEY, actor_id INTEGER, action TEXT NOT NULL,
          entity_type TEXT NOT NULL, entity_id INTEGER, details TEXT NOT NULL,
          created_at TEXT NOT NULL
        );
        CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit_log
          BEGIN SELECT RAISE(ABORT,'Audit records are immutable'); END;
        CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit_log
          BEGIN SELECT RAISE(ABORT,'Audit records are immutable'); END;
        CREATE TABLE IF NOT EXISTS notifications(
          id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
          booking_id INTEGER, channel TEXT NOT NULL, message TEXT NOT NULL,
          status TEXT NOT NULL CHECK(status IN ('Queued','SentDemo','Retry')),
          attempts INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL
        );
        """)
        self.db.commit()

    @staticmethod
    def _dt(value):
        if isinstance(value, datetime): return value
        try: return datetime.fromisoformat(value)
        except (TypeError, ValueError): raise CRBSError("Use ISO datetime, e.g. 2026-10-20T09:00.")

    @staticmethod
    def _iso(value):
        return value.isoformat(timespec="minutes")

    def _now(self):
        return datetime.now().replace(microsecond=0)

    def _actor(self, user_id, roles=None):
        row = self.db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        if not row or not row["active"]:
            raise CRBSError("User is missing or disabled.")
        if roles and row["role"] not in roles:
            self._audit(user_id, "AUTHORIZATION_DENIED", "User", user_id, f"required={','.join(roles)}")
            self.db.commit()
            raise CRBSError("Authorization denied: role is not permitted.")
        return row

    def _audit(self, actor_id, action, entity_type, entity_id, details=""):
        self.db.execute("""INSERT INTO audit_log(actor_id,action,entity_type,entity_id,details,created_at)
                           VALUES(?,?,?,?,?,?)""",
                        (actor_id, action, entity_type, entity_id, details, self._now().isoformat()))

    def _notify(self, user_id, booking_id, message):
        status = "SentDemo" if self.notification_available else "Retry"
        self.db.execute("""INSERT INTO notifications(user_id,booking_id,channel,message,status,attempts,created_at)
                           VALUES(?,?,?,?,?,?,?)""",
                        (user_id, booking_id, "IN_APP_DEMO", message, status,
                         1 if not self.notification_available else 0, self._now().isoformat()))

    def add_user(self, display_name, role, email=""):
        if role not in ROLES: raise CRBSError("Invalid role.")
        cur = self.db.execute("INSERT INTO users(display_name,role,email) VALUES(?,?,?)",
                              (display_name, role, email))
        self.db.commit()
        return cur.lastrowid

    def register_user(self, display_name, role, email, password):
        """Demo registration using PBKDF2. Production should use campus SSO and policy controls."""
        import hashlib, os
        if not display_name or not display_name.strip(): raise CRBSError("Display name is required.")
        if not email or "@" not in email: raise CRBSError("A valid email is required.")
        if not isinstance(password, str) or len(password) < 10: raise CRBSError("Password must contain at least 10 characters.")
        if role not in ROLES: raise CRBSError("Invalid role.")
        salt=os.urandom(16)
        digest=hashlib.pbkdf2_hmac("sha256",password.encode(),salt,200_000)
        # Separate auth table keeps add_user as a test/demo fixture helper.
        self.db.execute("CREATE TABLE IF NOT EXISTS auth_credentials(user_id INTEGER PRIMARY KEY REFERENCES users(id), salt BLOB NOT NULL, password_hash BLOB NOT NULL, failed_attempts INTEGER NOT NULL DEFAULT 0, locked_until TEXT)")
        cur=self.db.execute("INSERT INTO users(display_name,role,email) VALUES(?,?,?)",(display_name.strip(),role,email.strip().lower()))
        self.db.execute("INSERT INTO auth_credentials(user_id,salt,password_hash) VALUES(?,?,?)",(cur.lastrowid,salt,digest))
        self._audit(cur.lastrowid,"ACCOUNT_REGISTERED","User",cur.lastrowid,"self-service registration")
        self.db.commit()
        return cur.lastrowid

    def login(self, email, password, now=None):
        """Return user id on success. Five failures lock the demo account for 15 minutes."""
        import hashlib
        self.db.execute("CREATE TABLE IF NOT EXISTS auth_credentials(user_id INTEGER PRIMARY KEY REFERENCES users(id), salt BLOB NOT NULL, password_hash BLOB NOT NULL, failed_attempts INTEGER NOT NULL DEFAULT 0, locked_until TEXT)")
        row=self.db.execute("SELECT u.id,u.active,c.* FROM users u JOIN auth_credentials c ON c.user_id=u.id WHERE lower(u.email)=?",((email or "").strip().lower(),)).fetchone()
        if not row or not row["active"]: raise CRBSError("Invalid credentials or disabled account.")
        current=now or self._now()
        if row["locked_until"] and self._dt(row["locked_until"]) > current: raise CRBSError("Account temporarily locked; try again later.")
        digest=hashlib.pbkdf2_hmac("sha256",(password or "").encode(),row["salt"],200_000)
        import hmac
        if not hmac.compare_digest(digest,row["password_hash"]):
            failures=row["failed_attempts"]+1
            locked=(current+timedelta(minutes=15)).isoformat() if failures>=5 else None
            self.db.execute("UPDATE auth_credentials SET failed_attempts=?,locked_until=? WHERE user_id=?",(failures,locked,row["id"]))
            self._audit(row["id"],"LOGIN_FAILED","User",row["id"],f"failed_attempts={failures}")
            self.db.commit()
            raise CRBSError("Invalid credentials.")
        self.db.execute("UPDATE auth_credentials SET failed_attempts=0,locked_until=NULL WHERE user_id=?",(row["id"],))
        self._audit(row["id"],"LOGIN_SUCCEEDED","User",row["id"])
        self.db.commit()
        return row["id"]

    def set_user_active(self, actor_id, target_id, active):
        self._actor(actor_id, {"System Admin"})
        cur = self.db.execute("UPDATE users SET active=? WHERE id=?", (int(bool(active)), target_id))
        if cur.rowcount != 1: raise CRBSError("User does not exist.")
        self._audit(actor_id, "ACCOUNT_ENABLED" if active else "ACCOUNT_DISABLED", "User", target_id)
        self.db.commit()

    def assign_role(self, actor_id, target_id, role):
        self._actor(actor_id, {"System Admin"})
        if role not in ROLES: raise CRBSError("Invalid role.")
        cur = self.db.execute("UPDATE users SET role=? WHERE id=?", (role, target_id))
        if cur.rowcount != 1: raise CRBSError("User does not exist.")
        self._audit(actor_id, "ROLE_ASSIGNED", "User", target_id, f"role={role}")
        self.db.commit()

    def add_resource(self, name, kind, capacity=1, restricted=False, allowed_roles=None):
        """Fixture/setup helper for the prototype; application flows should use create_resource/update_resource."""
        if kind not in {"Room", "Seminar Room", "Equipment"}: raise CRBSError("Invalid resource kind.")
        if capacity < 1: raise CRBSError("Capacity must be >= 1.")
        allowed = ",".join(allowed_roles or ["Lecturer","Facility Staff","System Admin"])
        cur = self.db.execute("""INSERT INTO resources(name,kind,capacity,restricted,allowed_roles)
                                 VALUES(?,?,?,?,?)""",
                              (name, kind, capacity, int(restricted), allowed))
        self.db.commit()
        return cur.lastrowid

    def create_resource(self, actor_id, name, kind, capacity=1, restricted=False, allowed_roles=None):
        """Create a catalogue item through an authorized Facility Staff operation."""
        actor = self._actor(actor_id, {"Facility Staff"})
        if not isinstance(name, str) or not name.strip():
            raise CRBSError("Resource name is required.")
        if kind not in {"Room", "Seminar Room", "Equipment"}:
            raise CRBSError("Invalid resource kind.")
        if not isinstance(capacity, int) or capacity < 1:
            raise CRBSError("Capacity must be >= 1.")
        allowed_roles = allowed_roles or ["Lecturer", "Facility Staff", "System Admin"]
        if any(role not in ROLES for role in allowed_roles):
            raise CRBSError("Invalid role in resource allow-list.")
        allowed = ",".join(allowed_roles)
        cur = self.db.execute(
            "INSERT INTO resources(name,kind,capacity,restricted,allowed_roles) VALUES(?,?,?,?,?)",
            (name.strip(), kind, capacity, int(bool(restricted)), allowed))
        rid = cur.lastrowid
        self._audit(actor["id"], "RESOURCE_CREATED", "Resource", rid,
                    f"name={name.strip()}; kind={kind}; capacity={capacity}; restricted={bool(restricted)}")
        self.db.commit()
        return rid

    def update_resource(self, actor_id, resource_id, *, name=None, kind=None, capacity=None,
                        restricted=None, allowed_roles=None, active=None):
        """Update catalogue attributes; maintenance is controlled by incident workflows."""
        actor = self._actor(actor_id, {"Facility Staff"})
        current = self.db.execute("SELECT * FROM resources WHERE id=?", (resource_id,)).fetchone()
        if not current:
            raise CRBSError("Resource does not exist.")
        new_name = current["name"] if name is None else name.strip() if isinstance(name, str) else ""
        new_kind = current["kind"] if kind is None else kind
        new_capacity = current["capacity"] if capacity is None else capacity
        new_restricted = current["restricted"] if restricted is None else int(bool(restricted))
        new_active = current["active"] if active is None else int(bool(active))
        if not new_name:
            raise CRBSError("Resource name is required.")
        if new_kind not in {"Room", "Seminar Room", "Equipment"}:
            raise CRBSError("Invalid resource kind.")
        if not isinstance(new_capacity, int) or new_capacity < 1:
            raise CRBSError("Capacity must be >= 1.")
        new_allowed = current["allowed_roles"]
        if allowed_roles is not None:
            if any(role not in ROLES for role in allowed_roles):
                raise CRBSError("Invalid role in resource allow-list.")
            new_allowed = ",".join(allowed_roles)
        self.db.execute(
            "UPDATE resources SET name=?,kind=?,capacity=?,restricted=?,allowed_roles=?,active=? WHERE id=?",
            (new_name, new_kind, new_capacity, new_restricted, new_allowed, new_active, resource_id))
        self._audit(actor["id"], "RESOURCE_UPDATED", "Resource", resource_id,
                    f"name={new_name}; kind={new_kind}; capacity={new_capacity}; restricted={bool(new_restricted)}; active={bool(new_active)}")
        self.db.commit()

    def _can_view_resource(self, user, resource):
        if not resource["restricted"]: return True
        return user["role"] in resource["allowed_roles"].split(",")

    def search_resources(self, user_id, kind=None, min_capacity=1, start_time=None, end_time=None):
        user = self._actor(user_id, {"Student","Lecturer","Facility Staff","System Admin"})
        if min_capacity < 1: raise CRBSError("Minimum capacity must be >= 1.")
        if (start_time is None) != (end_time is None): raise CRBSError("Provide both start and end time.")
        if start_time is not None:
            start, end = self._dt(start_time), self._dt(end_time)
            if end <= start: raise CRBSError("End time must be later than start time.")
        rows = self.db.execute("SELECT * FROM resources WHERE active=1 AND capacity>=? ORDER BY name",
                               (min_capacity,)).fetchall()
        results=[]
        for r in rows:
            if kind and r["kind"] != kind: continue
            if not self._can_view_resource(user, r): continue
            if r["maintenance"]: continue
            if start_time is not None and not self.is_available(r["id"], start_time, end_time):
                continue
            results.append(r)
        return results

    def is_available(self, resource_id, start_time, end_time, ignore_booking_id=None):
        start, end = self._dt(start_time), self._dt(end_time)
        if end <= start: raise CRBSError("End time must be later than start time.")
        r = self.db.execute("SELECT active,maintenance FROM resources WHERE id=?", (resource_id,)).fetchone()
        if not r or not r["active"] or r["maintenance"]: return False
        sql = """SELECT 1 FROM bookings WHERE resource_id=?
                 AND status IN ('Pending','Approved') AND start_time < ? AND end_time > ?"""
        args=[resource_id,self._iso(end),self._iso(start)]
        if ignore_booking_id is not None:
            sql += " AND id != ?"; args.append(ignore_booking_id)
        sql += " LIMIT 1"
        if self.db.execute(sql,args).fetchone() is not None:
            return False
        item_sql = """SELECT 1 FROM booking_items i JOIN bookings b ON b.id=i.booking_id
                      WHERE i.resource_id=? AND b.status IN ('Pending','Approved')
                      AND b.start_time < ? AND b.end_time > ?"""
        item_args=[resource_id,self._iso(end),self._iso(start)]
        if ignore_booking_id is not None:
            item_sql += " AND b.id != ?"; item_args.append(ignore_booking_id)
        item_sql += " LIMIT 1"
        return self.db.execute(item_sql,item_args).fetchone() is None

    def _validate_lead_time(self, role, start):
        now=self._now()
        days=7 if role=="Student" else 30
        if start < now: raise CRBSError("Booking start time must be in the future.")
        if start > now + timedelta(days=days):
            raise CRBSError(f"{role} bookings may be made at most {days} days in advance.")

    def create_booking(self, user_id, resource_id, start_time, end_time, purpose,
                       attendees=1, support_notes="", now=None, bundled_equipment_ids=None):
        user=self._actor(user_id, {"Student","Lecturer"})
        resource=self.db.execute("SELECT * FROM resources WHERE id=?", (resource_id,)).fetchone()
        if not resource or not resource["active"]: raise CRBSError("Resource does not exist or is inactive.")
        if not self._can_view_resource(user, resource): raise CRBSError("Authorization denied for restricted resource.")
        start,end=self._dt(start_time),self._dt(end_time)
        if end <= start: raise CRBSError("End time must be later than start time.")
        if not purpose or not purpose.strip(): raise CRBSError("Booking purpose is required.")
        if not isinstance(attendees,int) or attendees < 1: raise CRBSError("Attendees must be at least 1.")
        if resource["kind"] in {"Room","Seminar Room"} and attendees > resource["capacity"]:
            raise CRBSError("Attendees exceed resource capacity.")
        self._validate_lead_time(user["role"], start)
        if resource["kind"]=="Seminar Room" and user["role"]=="Lecturer" and end-start > timedelta(hours=4):
            raise CRBSError("Lecturer seminar-room booking duration cannot exceed 4 hours.")
        if resource["maintenance"]: raise CRBSError("Resource is under maintenance.")
        bundle_ids = list(dict.fromkeys(bundled_equipment_ids or []))
        if resource_id in bundle_ids: raise CRBSError("Primary resource cannot also be listed as bundled equipment.")
        bundle_rows = []
        for equipment_id in bundle_ids:
            item = self.db.execute("SELECT * FROM resources WHERE id=?", (equipment_id,)).fetchone()
            if not item or not item["active"]: raise CRBSError(f"Bundled equipment {equipment_id} does not exist or is inactive.")
            if item["kind"] != "Equipment": raise CRBSError("Bundled items must be equipment resources.")
            if not self._can_view_resource(user, item): raise CRBSError("Authorization denied for restricted bundled equipment.")
            if item["maintenance"]: raise CRBSError(f"Bundled equipment {item['name']} is under maintenance.")
            if not self.is_available(equipment_id, start_time, end_time):
                raise CRBSError(f"Bundled equipment {item['name']} is not available for the requested time slot.")
            bundle_rows.append(item)
        if user["role"]=="Student" and self.student_weekly_quota is not None:
            week_start=start.replace(hour=0,minute=0,second=0,microsecond=0)-timedelta(days=start.weekday())
            week_end=week_start+timedelta(days=7)
            rows=self.db.execute("""SELECT start_time,end_time FROM bookings
                WHERE user_id=? AND status IN ('Pending','Approved') AND start_time>=? AND start_time<?""",
                (user_id,self._iso(week_start),self._iso(week_end))).fetchall()
            used=sum((self._dt(x["end_time"])-self._dt(x["start_time"])).total_seconds()/3600 for x in rows)
            if used+(end-start).total_seconds()/3600 > self.student_weekly_quota:
                raise CRBSError(f"Student weekly booking limit is {self.student_weekly_quota} hours.")
        if not self.is_available(resource_id,start_time,end_time):
            raise CRBSError("Resource is not available for the requested time slot.")
        # SQLite transaction is used for the demo. A production deployment needs
        # explicit concurrency testing and a stronger database-level locking strategy.
        try:
            self.db.execute("BEGIN IMMEDIATE")
            if not self.is_available(resource_id,start_time,end_time):
                raise CRBSError("Resource is not available for the requested time slot.")
            for item in bundle_rows:
                if not self.is_available(item["id"],start_time,end_time):
                    raise CRBSError(f"Bundled equipment {item['name']} is no longer available.")
            cur=self.db.execute("""INSERT INTO bookings(user_id,resource_id,start_time,end_time,purpose,
                attendees,support_notes,status,created_at) VALUES(?,?,?,?,?,?,?,'Pending',?)""",
                (user_id,resource_id,self._iso(start),self._iso(end),purpose.strip(),attendees,
                 support_notes.strip(),self._now().isoformat()))
            bid=cur.lastrowid
            self.db.execute("INSERT INTO booking_items(booking_id,resource_id,item_role) VALUES(?,?,'PRIMARY')", (bid,resource_id))
            for item in bundle_rows:
                self.db.execute("INSERT INTO booking_items(booking_id,resource_id,item_role) VALUES(?,?,'BUNDLED_EQUIPMENT')", (bid,item["id"]))
            self._audit(user_id,"BOOKING_SUBMITTED","Booking",bid,"status=Pending; bundled_equipment=" + ",".join(str(x["id"]) for x in bundle_rows))
            self._notify(user_id,bid,f"Booking #{bid} submitted: Pending")
            self.db.commit()
            return bid
        except Exception:
            self.db.rollback()
            raise

    def decide_booking(self, booking_id, actor_id, decision, reason=""):
        staff=self._actor(actor_id, {"Facility Staff"})
        if decision not in {"Approved","Rejected"}: raise CRBSError("Decision must be Approved or Rejected.")
        b=self.db.execute("SELECT * FROM bookings WHERE id=?", (booking_id,)).fetchone()
        if not b: raise CRBSError("Booking does not exist.")
        if b["status"]!="Pending": raise CRBSError("Only Pending bookings can be decided.")
        if decision=="Approved":
            if not self.is_available(b["resource_id"],b["start_time"],b["end_time"],ignore_booking_id=booking_id):
                raise CRBSError("Resource is no longer available.")
            item_rows=self.db.execute("SELECT i.resource_id,r.maintenance,r.active,r.name FROM booking_items i JOIN resources r ON r.id=i.resource_id WHERE i.booking_id=?",(booking_id,)).fetchall()
            for item in item_rows:
                if not item["active"] or item["maintenance"]:
                    raise CRBSError(f"Resource {item['name']} is under maintenance or inactive.")
                if not self.is_available(item["resource_id"],b["start_time"],b["end_time"],ignore_booking_id=booking_id):
                    raise CRBSError(f"Resource {item['name']} is no longer available.")
        self.db.execute("UPDATE bookings SET status=?,decision_reason=? WHERE id=?",
                        (decision,reason.strip(),booking_id))
        self._audit(actor_id,"BOOKING_"+decision.upper(),"Booking",booking_id,reason.strip())
        self._notify(b["user_id"],booking_id,f"Booking #{booking_id} status changed: {decision}")
        self.db.commit()

    def cancel_booking(self, booking_id, requester_id, now=None):
        b=self.db.execute("SELECT * FROM bookings WHERE id=?", (booking_id,)).fetchone()
        if not b: raise CRBSError("Booking does not exist.")
        user=self._actor(requester_id, {"Student","Lecturer"})
        if b["user_id"]!=requester_id:
            self._audit(requester_id,"AUTHORIZATION_DENIED","Booking",booking_id,"cancel other user's booking")
            self.db.commit()
            raise CRBSError("Authorization denied: can cancel only your own booking.")
        if b["status"] not in {"Pending","Approved"}: raise CRBSError("Only Pending or Approved bookings can be cancelled.")
        current=now or self._now()
        if self._dt(b["start_time"])-current < timedelta(hours=2):
            raise CRBSError("Cancellation requires at least 2 hours before start time.")
        self.db.execute("UPDATE bookings SET status='Cancelled' WHERE id=?", (booking_id,))
        self._audit(requester_id,"BOOKING_CANCELLED","Booking",booking_id,"status=Cancelled")
        self._notify(requester_id,booking_id,f"Booking #{booking_id} cancelled")
        self.db.commit()

    def checkout_equipment(self, booking_id, staff_id, now=None, resource_id=None):
        self._actor(staff_id, {"Facility Staff"})
        b=self.db.execute("SELECT * FROM bookings WHERE id=?", (booking_id,)).fetchone()
        if not b: raise CRBSError("Booking does not exist.")
        if b["status"]!="Approved": raise CRBSError("Checkout requires an Approved booking.")
        item_sql = """SELECT r.*,i.item_role FROM booking_items i JOIN resources r ON r.id=i.resource_id
                      WHERE i.booking_id=? AND r.kind='Equipment'"""
        item_args=[booking_id]
        if resource_id is not None:
            item_sql += " AND r.id=?"; item_args.append(resource_id)
        item_sql += " ORDER BY CASE WHEN i.item_role='PRIMARY' THEN 0 ELSE 1 END, r.id LIMIT 1"
        equipment=self.db.execute(item_sql,item_args).fetchone()
        if not equipment: raise CRBSError("No equipment item in this booking matches the checkout request.")
        if equipment["maintenance"] or not equipment["active"]: raise CRBSError("Checkout blocked: equipment is under maintenance or inactive.")
        if self.db.execute("SELECT 1 FROM equipment_transactions WHERE booking_id=? AND resource_id=? AND checkin_at IS NULL",
                           (booking_id,equipment["id"])).fetchone():
            raise CRBSError("Equipment is already checked out for this booking.")
        when=now or self._now()
        cur=self.db.execute("""INSERT INTO equipment_transactions(booking_id,resource_id,checkout_staff_id,checkout_at)
                               VALUES(?,?,?,?)""",
                            (booking_id,equipment["id"],staff_id,when.isoformat()))
        txid=cur.lastrowid
        self._audit(staff_id,"EQUIPMENT_CHECKED_OUT","EquipmentTransaction",txid,f"booking_id={booking_id}")
        self.db.commit()
        return txid

    def checkin_equipment(self, transaction_id, staff_id, condition, notes="", now=None):
        self._actor(staff_id, {"Facility Staff"})
        if condition not in CONDITIONS: raise CRBSError("Condition must be Good, Damaged, or Missing.")
        tx=self.db.execute("SELECT * FROM equipment_transactions WHERE id=?", (transaction_id,)).fetchone()
        if not tx: raise CRBSError("Checkout transaction does not exist.")
        if tx["checkin_at"] is not None: raise CRBSError("Equipment has already been checked in.")
        when=now or self._now()
        self.db.execute("""UPDATE equipment_transactions SET checkin_staff_id=?,checkin_at=?,condition=?,notes=?
                           WHERE id=?""", (staff_id,when.isoformat(),condition,notes.strip(),transaction_id))
        self._audit(staff_id,"EQUIPMENT_CHECKED_IN","EquipmentTransaction",transaction_id,
                    f"condition={condition}; notes={notes.strip()}")
        if condition in {"Damaged","Missing"}:
            resource_id=tx["resource_id"]
            cur=self.db.execute("""INSERT INTO maintenance_incidents(resource_id,opened_by,description,status,opened_at)
                                   VALUES(?,?,?,'Open',?)""",
                                (resource_id,staff_id,f"Returned equipment condition: {condition}. {notes.strip()}",
                                 when.isoformat()))
            self.db.execute("UPDATE resources SET maintenance=1 WHERE id=?", (resource_id,))
            self._audit(staff_id,"MAINTENANCE_OPENED","MaintenanceIncident",cur.lastrowid,
                        f"resource_id={resource_id}; condition={condition}")
        self.db.commit()

    def log_maintenance(self, resource_id, staff_id, description):
        self._actor(staff_id, {"Facility Staff"})
        if not description or not description.strip(): raise CRBSError("Maintenance description is required.")
        r=self.db.execute("SELECT * FROM resources WHERE id=?", (resource_id,)).fetchone()
        if not r: raise CRBSError("Resource does not exist.")
        cur=self.db.execute("""INSERT INTO maintenance_incidents(resource_id,opened_by,description,status,opened_at)
                               VALUES(?,?,?,'Open',?)""",
                            (resource_id,staff_id,description.strip(),self._now().isoformat()))
        self.db.execute("UPDATE resources SET maintenance=1 WHERE id=?", (resource_id,))
        self._audit(staff_id,"MAINTENANCE_OPENED","MaintenanceIncident",cur.lastrowid,
                    f"resource_id={resource_id}")
        self.db.commit()
        return cur.lastrowid

    def close_maintenance(self, incident_id, staff_id, resolution):
        self._actor(staff_id, {"Facility Staff"})
        if not resolution or not resolution.strip(): raise CRBSError("Resolution is required.")
        inc=self.db.execute("SELECT * FROM maintenance_incidents WHERE id=?", (incident_id,)).fetchone()
        if not inc: raise CRBSError("Maintenance incident does not exist.")
        if inc["status"]!="Open": raise CRBSError("Incident is already closed.")
        self.db.execute("""UPDATE maintenance_incidents SET status='Closed',closed_by=?,closed_at=?,resolution=?
                           WHERE id=?""",
                        (staff_id,self._now().isoformat(),resolution.strip(),incident_id))
        still_open=self.db.execute("SELECT 1 FROM maintenance_incidents WHERE resource_id=? AND status='Open' AND id!=?",
                                   (inc["resource_id"],incident_id)).fetchone()
        if not still_open: self.db.execute("UPDATE resources SET maintenance=0 WHERE id=?", (inc["resource_id"],))
        self._audit(staff_id,"MAINTENANCE_CLOSED","MaintenanceIncident",incident_id,resolution.strip())
        self.db.commit()

    def list_bookings(self, user_id=None):
        sql="""SELECT b.*,u.display_name requester,r.name resource,r.kind FROM bookings b
               JOIN users u ON u.id=b.user_id JOIN resources r ON r.id=b.resource_id"""
        args=()
        if user_id is not None: sql+=" WHERE b.user_id=?"; args=(user_id,)
        return self.db.execute(sql+" ORDER BY b.id",args).fetchall()

    def audit_entries(self):
        return self.db.execute("SELECT * FROM audit_log ORDER BY id").fetchall()

    def notifications_for(self, user_id):
        return self.db.execute("SELECT * FROM notifications WHERE user_id=? ORDER BY id",(user_id,)).fetchall()

    def close(self): self.db.close()

if __name__ == "__main__":
    app=CRBS()
    student=app.add_user("Demo Student","Student")
    lecturer=app.add_user("Demo Lecturer","Lecturer")
    staff=app.add_user("Demo Facility Staff","Facility Staff")
    room=app.add_resource("Room A101","Room",capacity=30)
    equipment=app.add_resource("Projector P01","Equipment")
    start=(datetime.now()+timedelta(days=1)).replace(hour=9,minute=0,second=0,microsecond=0)
    bid=app.create_booking(student,room,start,start+timedelta(hours=1),"Group project",6)
    app.decide_booking(bid,staff,"Approved")
    print("Created demo booking:",dict(app.list_bookings()[0]))
    print("Notification records:",len(app.notifications_for(student)))
    app.close()
