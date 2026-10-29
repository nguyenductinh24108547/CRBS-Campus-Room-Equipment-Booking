"""Prototype regression tests (PT-01 onward), not the original group application tests.

These tests exercise src/crbs.py, the educational Python/SQLite prototype only.
"""
import os, sys, unittest
from datetime import datetime, timedelta
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from crbs import CRBS, CRBSError

class TestCRBS(unittest.TestCase):
    def setUp(self):
        self.app = CRBS()
        self.student = self.app.add_user("Student One", "Student")
        self.student2 = self.app.add_user("Student Two", "Student")
        self.lecturer = self.app.add_user("Lecturer One", "Lecturer")
        self.staff = self.app.add_user("Facility Staff", "Facility Staff")
        self.admin = self.app.add_user("System Admin", "System Admin")
        self.room = self.app.add_resource("A101", "Room", 30)
        self.room2 = self.app.add_resource("A102", "Room", 30)
        self.seminar = self.app.add_resource("Seminar Hall", "Seminar Room", 100)
        self.projector = self.app.add_resource("Projector P01", "Equipment")
        self.vip = self.app.add_resource("VIP Lab", "Room", 20, restricted=True,
                                         allowed_roles=["Lecturer","Facility Staff","System Admin"])
        self.base = (datetime.now()+timedelta(days=2)).replace(hour=9, minute=0, second=0, microsecond=0)

    def tearDown(self): self.app.close()

    def slot(self, offset_hours=0, duration=1, days=2):
        start=(datetime.now()+timedelta(days=days)).replace(hour=9,minute=0,second=0,microsecond=0)+timedelta(hours=offset_hours)
        return start, start+timedelta(hours=duration)

    def book(self, user=None, resource=None, start=None, end=None, purpose="Group project", attendees=1):
        start = start or self.base
        end = end or start+timedelta(hours=1)
        return self.app.create_booking(user or self.student, resource or self.room,
              start.isoformat(timespec="minutes"), end.isoformat(timespec="minutes"), purpose, attendees)

    # PT-02 / REQ-02: valid booking creates Pending
    def test_PT02_valid_booking_pending_and_acknowledgement(self):
        bid=self.book(attendees=6)
        b=self.app.list_bookings()[0]
        self.assertEqual(b["id"],bid); self.assertEqual(b["status"],"Pending")
        self.assertEqual(len(self.app.notifications_for(self.student)),1)

    # PT-03 / REQ-01: overlapping booking is blocked
    def test_PT03_overlapping_booking_rejected(self):
        self.book()
        with self.assertRaisesRegex(CRBSError,"not available"):
            self.book(start=self.base+timedelta(minutes=30),end=self.base+timedelta(minutes=90))

    # PT-04 / REQ-01: adjacent slots allowed
    def test_PT04_adjacent_slot_allowed(self):
        self.book()
        self.book(start=self.base+timedelta(hours=1),end=self.base+timedelta(hours=2))
        self.assertEqual(len(self.app.list_bookings()),2)

    # PT-05 / DR-03: invalid interval rejected
    def test_PT05_invalid_interval_rejected(self):
        with self.assertRaisesRegex(CRBSError,"later"):
            self.book(start=self.base,end=self.base)

    # PT-06 / REQ-03: staff approves and notifies
    def test_PT06_staff_approves_pending_booking(self):
        bid=self.book()
        self.app.decide_booking(bid,self.staff,"Approved")
        self.assertEqual(self.app.list_bookings()[0]["status"],"Approved")
        self.assertEqual(len(self.app.notifications_for(self.student)),2)

    # PT-07 / REQ-09: student cannot approve
    def test_PT07_student_cannot_approve(self):
        bid=self.book()
        with self.assertRaisesRegex(CRBSError,"Authorization denied"):
            self.app.decide_booking(bid,self.student,"Approved")

    # PT-08 / REQ-03: only Pending can be decided
    def test_PT08_cannot_decide_booking_twice(self):
        bid=self.book()
        self.app.decide_booking(bid,self.staff,"Rejected","Not enough details")
        with self.assertRaisesRegex(CRBSError,"Only Pending"):
            self.app.decide_booking(bid,self.staff,"Approved")

    # PT-09 / REQ-09: student cannot view restricted resource
    def test_PT09_restricted_resource_hidden_from_student(self):
        found=self.app.search_resources(self.student,kind="Room")
        self.assertNotIn(self.vip,[r["id"] for r in found])

    # PT-10 / REQ-09: student cannot book restricted resource
    def test_PT10_restricted_resource_booking_denied(self):
        with self.assertRaisesRegex(CRBSError,"restricted"):
            self.book(resource=self.vip)

    # PT-11 / BR-01: Student lead time <=7 days
    def test_PT11_student_cannot_book_beyond_7_days(self):
        start=(datetime.now()+timedelta(days=8)).replace(hour=9,minute=0,second=0,microsecond=0)
        with self.assertRaisesRegex(CRBSError,"7 days"):
            self.book(start=start,end=start+timedelta(hours=1))

    # PT-12 / BR-01: Lecturer can book within 30 days
    def test_PT12_lecturer_can_book_within_30_days(self):
        start=(datetime.now()+timedelta(days=20)).replace(hour=9,minute=0,second=0,microsecond=0)
        bid=self.book(user=self.lecturer,start=start,end=start+timedelta(hours=1))
        self.assertEqual(self.app.list_bookings()[0]["status"],"Pending")

    # PT-13 / NFR-D10: Lecturer seminar duration max 4h
    def test_PT13_lecturer_seminar_over_4h_rejected(self):
        start=self.base
        with self.assertRaisesRegex(CRBSError,"4 hours"):
            self.book(user=self.lecturer,resource=self.seminar,start=start,end=start+timedelta(hours=5),
                      purpose="Official seminar",attendees=40)

    # PT-14 / BR-05: student weekly quota enforced
    def test_PT14_student_weekly_quota_enforced(self):
        # BR-05: enforce the agreed 10-hour student weekly booking limit.
        self.app.student_weekly_quota = 10
        # Schedule both bookings soon, in the same week, and within the 7-day lead-time.
        start=(datetime.now()+timedelta(days=2)).replace(hour=7,minute=0,second=0,microsecond=0)
        self.book(start=start,end=start+timedelta(hours=10),attendees=1)
        # A different room must not reset the same student's weekly quota.
        second=start+timedelta(hours=10)
        with self.assertRaisesRegex(CRBSError,"10 hours"):
            self.book(resource=self.room2,start=second,end=second+timedelta(hours=1))
        # The rejected request must not create a second booking.
        self.assertEqual(len(self.app.list_bookings()),1)

    # PT-15 / REQ-06: exact 2 hours cancellation allowed
    def test_PT15_cancel_exactly_two_hours_before(self):
        start=self.base+timedelta(days=1)
        bid=self.book(start=start,end=start+timedelta(hours=1))
        self.app.cancel_booking(bid,self.student,now=start-timedelta(hours=2))
        self.assertEqual(self.app.list_bookings()[0]["status"],"Cancelled")

    # PT-16 / REQ-06: less than 2 hours rejected
    def test_PT16_cancel_under_two_hours_rejected(self):
        start=self.base+timedelta(days=1)
        bid=self.book(start=start,end=start+timedelta(hours=1))
        with self.assertRaisesRegex(CRBSError,"at least 2 hours"):
            self.app.cancel_booking(bid,self.student,now=start-timedelta(hours=1,minutes=59))

    # PT-17 / DR-09: only owner can cancel
    def test_PT17_other_user_cannot_cancel(self):
        bid=self.book()
        with self.assertRaisesRegex(CRBSError,"own booking"):
            self.app.cancel_booking(bid,self.student2,now=self.base-timedelta(hours=3))

    # PT-01 / REQ-04 / historical TC-05 defect retest: maintenance blocks checkout
    def test_PT01_maintenance_blocks_checkout_retest_of_TC05(self):
        bid=self.book(user=self.lecturer,resource=self.projector)
        self.app.decide_booking(bid,self.staff,"Approved")
        self.app.log_maintenance(self.projector,self.staff,"Projector lamp fault")
        with self.assertRaisesRegex(CRBSError,"maintenance"):
            self.app.checkout_equipment(bid,self.staff)
        self.assertEqual(self.app.db.execute("SELECT count(*) FROM equipment_transactions").fetchone()[0],0)

    # PT-18 / REQ-04: valid checkout records staff and timestamp
    def test_PT18_checkout_valid_approved_equipment(self):
        bid=self.book(user=self.lecturer,resource=self.projector)
        self.app.decide_booking(bid,self.staff,"Approved")
        tx=self.app.checkout_equipment(bid,self.staff,now=self.base)
        row=self.app.db.execute("SELECT * FROM equipment_transactions WHERE id=?",(tx,)).fetchone()
        self.assertEqual(row["checkout_staff_id"],self.staff); self.assertIsNotNone(row["checkout_at"])

    # PT-19 / REQ-05: good check-in closes transaction
    def test_PT19_good_checkin_closes_transaction(self):
        bid=self.book(user=self.lecturer,resource=self.projector)
        self.app.decide_booking(bid,self.staff,"Approved")
        tx=self.app.checkout_equipment(bid,self.staff,now=self.base)
        self.app.checkin_equipment(tx,self.staff,"Good","Returned OK")
        row=self.app.db.execute("SELECT * FROM equipment_transactions WHERE id=?",(tx,)).fetchone()
        self.assertIsNotNone(row["checkin_at"]); self.assertEqual(row["condition"],"Good")

    # PT-20 / REQ-05, REQ-07: damaged return creates maintenance incident
    def test_PT20_damaged_checkin_opens_maintenance(self):
        bid=self.book(user=self.lecturer,resource=self.projector)
        self.app.decide_booking(bid,self.staff,"Approved")
        tx=self.app.checkout_equipment(bid,self.staff,now=self.base)
        self.app.checkin_equipment(tx,self.staff,"Damaged","Lens cracked")
        r=self.app.db.execute("SELECT maintenance FROM resources WHERE id=?",(self.projector,)).fetchone()
        self.assertEqual(r["maintenance"],1)
        self.assertEqual(self.app.db.execute("SELECT count(*) FROM maintenance_incidents").fetchone()[0],1)

    # PT-21 / REQ-07: maintenance removes resource from search
    def test_PT21_maintenance_resource_excluded_from_search(self):
        self.app.log_maintenance(self.room,self.staff,"Door lock broken")
        found=self.app.search_resources(self.student,kind="Room")
        self.assertNotIn(self.room,[r["id"] for r in found])

    # PT-22 / REQ-07: close incident clears maintenance
    def test_PT22_close_incident_restores_resource(self):
        iid=self.app.log_maintenance(self.room,self.staff,"Door lock broken")
        self.app.close_maintenance(iid,self.staff,"Lock repaired")
        r=self.app.db.execute("SELECT maintenance FROM resources WHERE id=?",(self.room,)).fetchone()
        self.assertEqual(r["maintenance"],0)

    # PT-23 / REQ-08: audit immutable
    def test_PT23_audit_update_delete_blocked(self):
        self.book()
        with self.assertRaisesRegex(Exception,"immutable"):
            self.app.db.execute("UPDATE audit_log SET details='tampered' WHERE id=1")
        self.app.db.rollback()
        with self.assertRaisesRegex(Exception,"immutable"):
            self.app.db.execute("DELETE FROM audit_log WHERE id=1")
        self.app.db.rollback()

    # PT-24 / REQ-10: notification outage doesn't block booking
    def test_PT24_notification_outage_does_not_block_booking(self):
        self.app.notification_available=False
        bid=self.book()
        self.assertTrue(bid)
        n=self.app.notifications_for(self.student)[0]
        self.assertEqual(n["status"],"Retry")

    # PT-25 / UC-14, UC-15: admin can assign role and audit
    def test_PT25_admin_assigns_role_and_audit(self):
        self.app.assign_role(self.admin,self.student2,"Lecturer")
        u=self.app.db.execute("SELECT role FROM users WHERE id=?",(self.student2,)).fetchone()
        self.assertEqual(u["role"],"Lecturer")
        self.assertIn("ROLE_ASSIGNED",[x["action"] for x in self.app.audit_entries()])

    # PT-26 / REQ-09: non-admin cannot assign role
    def test_PT26_staff_cannot_assign_role(self):
        with self.assertRaisesRegex(CRBSError,"Authorization denied"):
            self.app.assign_role(self.staff,self.student2,"System Admin")


    # PT-27 / DR-16: one booking contains the room and bundled equipment
    def test_PT27_room_and_bundled_equipment_are_one_request(self):
        start=self.base
        bid=self.app.create_booking(self.student,self.room,
            start.isoformat(timespec="minutes"),(start+timedelta(hours=1)).isoformat(timespec="minutes"),
            "Project presentation",6,"Need projector and microphone",bundled_equipment_ids=[self.projector])
        items=self.app.db.execute("SELECT resource_id,item_role FROM booking_items WHERE booking_id=? ORDER BY item_role",(bid,)).fetchall()
        self.assertEqual({r["resource_id"] for r in items},{self.room,self.projector})
        self.assertEqual(self.app.list_bookings()[0]["status"],"Pending")

    # PT-28 / REQ-11, UC-16: registration and login are demonstrable
    def test_PT28_register_and_login(self):
        user_id=self.app.register_user("New Student","Student","new.student@example.edu","A-strong-demo-password")
        self.assertEqual(self.app.login("new.student@example.edu","A-strong-demo-password"),user_id)
        with self.assertRaisesRegex(CRBSError,"Invalid credentials"):
            self.app.login("new.student@example.edu","wrong-password")


    # PT-29 / REQ-11: repeated invalid logins trigger temporary lockout
    def test_PT29_five_failed_logins_lock_account(self):
        user_id=self.app.register_user("Lock Test","Student","lock.test@example.edu","A-strong-demo-password")
        for _ in range(5):
            with self.assertRaisesRegex(CRBSError,"Invalid credentials"):
                self.app.login("lock.test@example.edu","wrong-password")
        with self.assertRaisesRegex(CRBSError,"temporarily locked"):
            self.app.login("lock.test@example.edu","A-strong-demo-password")

    # PT-30 / DR-16: bundled equipment conflict rejects the entire request
    def test_PT30_conflicting_bundled_equipment_rejects_whole_booking(self):
        start=self.base
        self.app.create_booking(self.student,self.room,start.isoformat(timespec="minutes"),
            (start+timedelta(hours=1)).isoformat(timespec="minutes"),"Room with projector",4,
            bundled_equipment_ids=[self.projector])
        with self.assertRaisesRegex(CRBSError,"not available"):
            self.app.create_booking(self.student2,self.room2,start.isoformat(timespec="minutes"),
                (start+timedelta(hours=1)).isoformat(timespec="minutes"),"Another room, same projector",4,
                bundled_equipment_ids=[self.projector])
        self.assertEqual(len(self.app.list_bookings()),1)

    # PT-31 / DR-08: invalid check-in condition is rejected
    def test_PT31_invalid_checkin_condition_rejected(self):
        start=self.base
        bid=self.book(user=self.lecturer,resource=self.projector,start=start,end=start+timedelta(hours=1))
        self.app.decide_booking(bid,self.staff,"Approved")
        tx=self.app.checkout_equipment(bid,self.staff,now=start)
        with self.assertRaisesRegex(CRBSError,"Condition must be"):
            self.app.checkin_equipment(tx,self.staff,"Unknown","invalid")

    # PT-32 / DR-16, REQ-07: maintenance on a bundled item rejects whole request
    def test_PT32_maintenance_bundled_item_rejects_request(self):
        self.app.log_maintenance(self.projector,self.staff,"Projector lens damaged")
        start=self.base
        with self.assertRaisesRegex(CRBSError,"under maintenance"):
            self.app.create_booking(self.student,self.room,start.isoformat(timespec="minutes"),
                (start+timedelta(hours=1)).isoformat(timespec="minutes"),"Room with projector",4,
                bundled_equipment_ids=[self.projector])
        self.assertEqual(len(self.app.list_bookings()),0)

    # PT-33 / REQ-13 / UC-18: catalogue maintenance is restricted to Facility Staff and audited.
    def test_PT33_resource_catalogue_create_update_is_authorized_and_audited(self):
        resource_id = self.app.create_resource(self.staff, "Lab C203", "Room", capacity=24)
        self.app.update_resource(self.staff, resource_id, name="Lab C203 Updated", capacity=28)
        resource = self.app.db.execute("SELECT * FROM resources WHERE id=?", (resource_id,)).fetchone()
        self.assertEqual(resource["name"], "Lab C203 Updated")
        self.assertEqual(resource["capacity"], 28)
        actions = [row["action"] for row in self.app.audit_entries()]
        self.assertIn("RESOURCE_CREATED", actions)
        self.assertIn("RESOURCE_UPDATED", actions)
        with self.assertRaisesRegex(CRBSError, "Authorization denied"):
            self.app.update_resource(self.student, resource_id, capacity=30)

    # PT-34 / TC-10 / REQ-02: purpose is mandatory.
    def test_PT34_booking_requires_purpose(self):
        with self.assertRaisesRegex(CRBSError, "purpose is required"):
            self.book(purpose="")

    # PT-35 / TC-09 and TC-13: users see their own booking records only.
    def test_PT35_booking_list_is_scoped_to_requester(self):
        own_id = self.book(user=self.student)
        self.book(user=self.student2, resource=self.room2)
        visible = self.app.list_bookings(user_id=self.student)
        self.assertEqual([row["id"] for row in visible], [own_id])

    # PT-36 / TC-16 / BR-03: a lecturer seminar within the provisional 4-hour limit is accepted.
    def test_PT36_lecturer_seminar_within_four_hours_succeeds(self):
        bid = self.book(user=self.lecturer, resource=self.seminar, start=self.base,
                        end=self.base + timedelta(hours=3), purpose="Official seminar", attendees=40)
        self.assertEqual(self.app.list_bookings()[0]["id"], bid)

    # PT-37 / TC-17 / HZ-01-HZ-06: approval revalidates bundled equipment.
    def test_PT37_approval_rechecks_maintenance_on_bundled_item(self):
        bid = self.book(user=self.student, resource=self.room, start=self.base,
                        end=self.base + timedelta(hours=1), purpose="Practice")
        self.app.db.execute("INSERT INTO booking_items(booking_id,resource_id,item_role) VALUES(?,?,'BUNDLED_EQUIPMENT')", (bid,self.projector))
        self.app.db.commit()
        self.app.log_maintenance(self.projector,self.staff,"Projector failure before approval")
        with self.assertRaisesRegex(CRBSError, "under maintenance or inactive"):
            self.app.decide_booking(bid,self.staff,"Approved")

    # PT-38 / TC-25 / REQ-11: invalid password is rejected at login.
    def test_PT38_invalid_login_password_rejected(self):
        self.app.register_user("New Student", "Student", "new.student@example.edu", "ValidPass123")
        with self.assertRaisesRegex(CRBSError, "Invalid credentials"):
            self.app.login("new.student@example.edu", "WrongPass123")

    # PT-39 / TC-27 / UC-14: admin can disable an account and the action is audited.
    def test_PT39_admin_disables_account_and_audits(self):
        target = self.app.add_user("Temporary User", "Student")
        self.app.set_user_active(self.admin, target, False)
        row = self.app.db.execute("SELECT active FROM users WHERE id=?", (target,)).fetchone()
        self.assertEqual(row["active"], 0)
        actions = [x["action"] for x in self.app.audit_entries()]
        self.assertIn("ACCOUNT_DISABLED", actions)

    # PT-40 / TC-11 / UC-05: Lecturer, as Booking Owner, can cancel their own booking.
    def test_PT40_lecturer_can_cancel_own_booking(self):
        bid = self.book(user=self.lecturer, start=self.base, end=self.base + timedelta(hours=1))
        self.app.cancel_booking(bid, self.lecturer, now=self.base - timedelta(hours=3))
        self.assertEqual(self.app.list_bookings()[0]["status"], "Cancelled")

if __name__ == "__main__":
    unittest.main(verbosity=2)
