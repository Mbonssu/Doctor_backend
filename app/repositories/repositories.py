from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import select, func, and_, or_, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..models.models import (
    User, Doctor, Appointment, Review, DoctorSchedule,
    DoctorTimeSlot, RefreshToken, FavoriteDoctor, Notification, AppointmentStatus
)


# ─── Base ─────────────────────────────────────────────────────────────────────

class BaseRepository:
    def __init__(self, db: AsyncSession):
        self.db = db


# ─── User ─────────────────────────────────────────────────────────────────────

class UserRepository(BaseRepository):

    async def get_by_id(self, user_id: int) -> Optional[User]:
        result = await self.db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> Optional[User]:
        result = await self.db.execute(select(User).where(User.email == email.lower().strip()))
        return result.scalar_one_or_none()

    async def create(self, email: str, hashed_password: str, first_name: str,
                     last_name: str, role: str = "patient", phone: Optional[str] = None) -> User:
        user = User(
            email=email.lower().strip(),
            hashed_password=hashed_password,
            first_name=first_name.strip(),
            last_name=last_name.strip(),
            role=role,
            phone=phone,
        )
        self.db.add(user)
        await self.db.flush()
        await self.db.refresh(user)
        return user

    async def update(self, user_id: int, **kwargs) -> Optional[User]:
        await self.db.execute(
            sa_update(User).where(User.id == user_id).values(**kwargs)
        )
        return await self.get_by_id(user_id)

    async def verify(self, user_id: int) -> None:
        await self.db.execute(
            sa_update(User).where(User.id == user_id).values(is_verified=True)
        )


# ─── Doctor ───────────────────────────────────────────────────────────────────

class DoctorRepository(BaseRepository):

    async def get_by_id(self, doctor_id: int) -> Optional[Doctor]:
        result = await self.db.execute(
            select(Doctor).options(selectinload(Doctor.user))
            .where(Doctor.id == doctor_id)
        )
        return result.scalar_one_or_none()

    async def get_by_user_id(self, user_id: int) -> Optional[Doctor]:
        result = await self.db.execute(
            select(Doctor).options(selectinload(Doctor.user))
            .where(Doctor.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def search(self, query: Optional[str] = None, specialty: Optional[str] = None,
                     city: Optional[str] = None, is_available: bool = True,
                     page: int = 1, page_size: int = 20):
        stmt = select(Doctor).options(selectinload(Doctor.user)).join(User)

        conditions = []
        if is_available:
            conditions.append(Doctor.is_available == True)
        if specialty:
            conditions.append(Doctor.specialty.ilike(f"%{specialty}%"))
        if city:
            conditions.append(Doctor.city.ilike(f"%{city}%"))
        if query:
            conditions.append(or_(
                User.first_name.ilike(f"%{query}%"),
                User.last_name.ilike(f"%{query}%"),
                Doctor.specialty.ilike(f"%{query}%"),
            ))
        if conditions:
            stmt = stmt.where(and_(*conditions))

        total_result = await self.db.execute(select(func.count()).select_from(stmt.subquery()))
        total = total_result.scalar_one()

        stmt = stmt.order_by(Doctor.rating.desc()).offset((page - 1) * page_size).limit(page_size)
        result = await self.db.execute(stmt)
        return result.scalars().all(), total

    async def get_top_rated(self, limit: int = 10) -> list[Doctor]:
        result = await self.db.execute(
            select(Doctor).options(selectinload(Doctor.user))
            .where(Doctor.is_available == True)
            .order_by(Doctor.rating.desc())
            .limit(limit)
        )
        return result.scalars().all()

    async def create(self, user_id: int, specialty: str, license_number: str,
                     **kwargs) -> Doctor:
        doctor = Doctor(user_id=user_id, specialty=specialty, license_number=license_number, **kwargs)
        self.db.add(doctor)
        await self.db.flush()
        await self.db.refresh(doctor)
        return doctor

    async def update(self, doctor_id: int, **kwargs) -> Optional[Doctor]:
        await self.db.execute(
            sa_update(Doctor).where(Doctor.id == doctor_id).values(**kwargs)
        )
        return await self.get_by_id(doctor_id)

    async def update_rating(self, doctor_id: int) -> None:
        result = await self.db.execute(
            select(func.avg(Review.rating), func.count(Review.id))
            .where(Review.doctor_id == doctor_id)
        )
        avg_rating, count = result.one()
        await self.db.execute(
            sa_update(Doctor).where(Doctor.id == doctor_id)
            .values(rating=round(float(avg_rating or 0), 1), total_reviews=count or 0)
        )


# ─── Schedule ─────────────────────────────────────────────────────────────────

class ScheduleRepository(BaseRepository):

    async def get_week_schedule(self, doctor_id: int) -> list[DoctorSchedule]:
        result = await self.db.execute(
            select(DoctorSchedule).where(DoctorSchedule.doctor_id == doctor_id)
            .order_by(DoctorSchedule.day_of_week)
        )
        return result.scalars().all()

    async def get_slots(self, doctor_id: int, day_of_week: Optional[int] = None) -> list[DoctorTimeSlot]:
        stmt = select(DoctorTimeSlot).where(DoctorTimeSlot.doctor_id == doctor_id)
        if day_of_week is not None:
            stmt = stmt.where(DoctorTimeSlot.day_of_week == day_of_week)
        stmt = stmt.order_by(DoctorTimeSlot.day_of_week, DoctorTimeSlot.time)
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def upsert_schedule(self, doctor_id: int, day_of_week: int,
                               is_working_day: bool, consult_duration_min: int,
                               break_duration_min: int, max_patients: int) -> DoctorSchedule:
        result = await self.db.execute(
            select(DoctorSchedule).where(
                DoctorSchedule.doctor_id == doctor_id,
                DoctorSchedule.day_of_week == day_of_week,
            )
        )
        schedule = result.scalar_one_or_none()
        if schedule:
            schedule.is_working_day = is_working_day
            schedule.consult_duration_min = consult_duration_min
            schedule.break_duration_min = break_duration_min
            schedule.max_patients = max_patients
        else:
            schedule = DoctorSchedule(
                doctor_id=doctor_id, day_of_week=day_of_week,
                is_working_day=is_working_day,
                consult_duration_min=consult_duration_min,
                break_duration_min=break_duration_min,
                max_patients=max_patients,
            )
            self.db.add(schedule)
        await self.db.flush()
        return schedule

    async def sync_slots(self, doctor_id: int, day_of_week: int, times: list[str]) -> list[DoctorTimeSlot]:
        """Remplace tous les créneaux d'un jour par la nouvelle liste."""
        # Désactiver les anciens
        await self.db.execute(
            sa_update(DoctorTimeSlot)
            .where(DoctorTimeSlot.doctor_id == doctor_id, DoctorTimeSlot.day_of_week == day_of_week)
            .values(is_active=False)
        )
        # Réactiver ou créer les nouveaux
        for time in times:
            result = await self.db.execute(
                select(DoctorTimeSlot).where(
                    DoctorTimeSlot.doctor_id == doctor_id,
                    DoctorTimeSlot.day_of_week == day_of_week,
                    DoctorTimeSlot.time == time,
                )
            )
            slot = result.scalar_one_or_none()
            if slot:
                slot.is_active = True
            else:
                self.db.add(DoctorTimeSlot(doctor_id=doctor_id, day_of_week=day_of_week, time=time))
        await self.db.flush()
        return await self.get_slots(doctor_id, day_of_week)


# ─── Appointment ──────────────────────────────────────────────────────────────

class AppointmentRepository(BaseRepository):

    async def get_by_id(self, apt_id: int) -> Optional[Appointment]:
        result = await self.db.execute(
            select(Appointment)
            .options(selectinload(Appointment.doctor_rel).selectinload(Doctor.user))
            .where(Appointment.id == apt_id)
        )
        return result.scalar_one_or_none()

    async def get_my_appointments(self, patient_id: int, status: Optional[str] = None,
                                   page: int = 1, page_size: int = 20):
        stmt = (
            select(Appointment)
            .options(selectinload(Appointment.doctor_rel).selectinload(Doctor.user))
            .where(Appointment.patient_id == patient_id)
        )
        if status:
            stmt = stmt.where(Appointment.status == status)

        total_result = await self.db.execute(select(func.count()).select_from(stmt.subquery()))
        total = total_result.scalar_one()

        stmt = stmt.order_by(Appointment.appointment_date.desc()).offset((page - 1) * page_size).limit(page_size)
        result = await self.db.execute(stmt)
        return result.scalars().all(), total

    async def get_doctor_appointments(self, doctor_id: int, status: Optional[str] = None,
                                       page: int = 1, page_size: int = 20):
        stmt = select(Appointment).where(Appointment.doctor_id == doctor_id)
        if status:
            stmt = stmt.where(Appointment.status == status)

        total_result = await self.db.execute(select(func.count()).select_from(stmt.subquery()))
        total = total_result.scalar_one()

        stmt = stmt.order_by(Appointment.appointment_date.asc()).offset((page - 1) * page_size).limit(page_size)
        result = await self.db.execute(stmt)
        return result.scalars().all(), total

    async def get_upcoming(self, patient_id: int, limit: int = 10) -> list[Appointment]:
        now = datetime.now(timezone.utc)
        result = await self.db.execute(
            select(Appointment)
            .options(selectinload(Appointment.doctor_rel).selectinload(Doctor.user))
            .where(
                Appointment.patient_id == patient_id,
                Appointment.appointment_date >= now,
                Appointment.status.in_(["pending", "confirmed"]),
            )
            .order_by(Appointment.appointment_date.asc())
            .limit(limit)
        )
        return result.scalars().all()

    async def get_next(self, patient_id: int) -> Optional[Appointment]:
        upcoming = await self.get_upcoming(patient_id, limit=1)
        return upcoming[0] if upcoming else None

    async def check_availability(self, doctor_id: int, appointment_date: datetime,
                                   duration_minutes: int) -> bool:
        from datetime import timedelta
        end_time = appointment_date + timedelta(minutes=duration_minutes)
        result = await self.db.execute(
            select(Appointment).where(
                Appointment.doctor_id == doctor_id,
                Appointment.status.in_(["pending", "confirmed"]),
                Appointment.appointment_date < end_time,
            )
        )
        conflicts = result.scalars().all()
        for apt in conflicts:
            apt_end = apt.appointment_date + timedelta(minutes=apt.duration_minutes)
            if apt.appointment_date < end_time and apt_end > appointment_date:
                return False
        return True

    async def create(self, **kwargs) -> Appointment:
        apt = Appointment(**kwargs)
        self.db.add(apt)
        await self.db.flush()
        await self.db.refresh(apt)
        return await self.get_by_id(apt.id)

    async def update(self, apt_id: int, **kwargs) -> Optional[Appointment]:
        await self.db.execute(sa_update(Appointment).where(Appointment.id == apt_id).values(**kwargs))
        return await self.get_by_id(apt_id)

    async def cancel(self, apt_id: int, cancelled_by: str, reason: str) -> Optional[Appointment]:
        return await self.update(
            apt_id,
            status=AppointmentStatus.cancelled,
            cancelled_by=cancelled_by,
            cancellation_reason=reason,
            cancelled_at=datetime.now(timezone.utc),
        )

    async def get_doctor_stats(self, doctor_id: int) -> dict:
        today = datetime.now(timezone.utc).date()
        today_count = await self.db.execute(
            select(func.count()).where(
                Appointment.doctor_id == doctor_id,
                func.date(Appointment.appointment_date) == today,
            )
        )
        pending_count = await self.db.execute(
            select(func.count()).where(
                Appointment.doctor_id == doctor_id,
                Appointment.status == "pending",
            )
        )
        month_count = await self.db.execute(
            select(func.count()).where(
                Appointment.doctor_id == doctor_id,
                func.extract("month", Appointment.appointment_date) == datetime.now().month,
                func.extract("year", Appointment.appointment_date) == datetime.now().year,
            )
        )
        return {
            "today": today_count.scalar_one(),
            "pending": pending_count.scalar_one(),
            "this_month": month_count.scalar_one(),
        }


# ─── Review ───────────────────────────────────────────────────────────────────

class ReviewRepository(BaseRepository):

    async def get_by_id(self, review_id: int) -> Optional[Review]:
        result = await self.db.execute(
            select(Review).options(selectinload(Review.patient))
            .where(Review.id == review_id)
        )
        return result.scalar_one_or_none()

    async def get_doctor_reviews(self, doctor_id: int, page: int = 1, page_size: int = 20):
        stmt = (
            select(Review).options(selectinload(Review.patient))
            .where(Review.doctor_id == doctor_id)
        )
        total_result = await self.db.execute(select(func.count()).select_from(stmt.subquery()))
        total = total_result.scalar_one()

        avg_result = await self.db.execute(
            select(func.avg(Review.rating)).where(Review.doctor_id == doctor_id)
        )
        avg = avg_result.scalar_one() or 0.0

        stmt = stmt.order_by(Review.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        result = await self.db.execute(stmt)
        return result.scalars().all(), total, round(float(avg), 1)

    async def create(self, doctor_id: int, patient_id: int, rating: int, comment: str) -> Review:
        review = Review(doctor_id=doctor_id, patient_id=patient_id, rating=rating, comment=comment)
        self.db.add(review)
        await self.db.flush()
        await self.db.refresh(review)
        return await self.get_by_id(review.id)

    async def update(self, review_id: int, **kwargs) -> Optional[Review]:
        await self.db.execute(sa_update(Review).where(Review.id == review_id).values(**kwargs))
        return await self.get_by_id(review_id)

    async def delete(self, review_id: int) -> None:
        result = await self.db.execute(select(Review).where(Review.id == review_id))
        review = result.scalar_one_or_none()
        if review:
            await self.db.delete(review)


# ─── Refresh token ────────────────────────────────────────────────────────────

class RefreshTokenRepository(BaseRepository):

    async def create(self, user_id: int, token: str, expires_at: datetime) -> RefreshToken:
        rt = RefreshToken(user_id=user_id, token=token, expires_at=expires_at)
        self.db.add(rt)
        await self.db.flush()
        return rt

    async def get(self, token: str) -> Optional[RefreshToken]:
        result = await self.db.execute(select(RefreshToken).where(RefreshToken.token == token))
        return result.scalar_one_or_none()

    async def revoke(self, token: str) -> None:
        await self.db.execute(sa_update(RefreshToken).where(RefreshToken.token == token).values(is_revoked=True))

    async def revoke_all_for_user(self, user_id: int) -> None:
        await self.db.execute(sa_update(RefreshToken).where(RefreshToken.user_id == user_id).values(is_revoked=True))


# ─── Notification ─────────────────────────────────────────────────────────────

class NotificationRepository(BaseRepository):

    async def create(self, user_id: int, title: str, message: str, notif_type: str = "info") -> Notification:
        notif = Notification(user_id=user_id, title=title, message=message, notif_type=notif_type)
        self.db.add(notif)
        await self.db.flush()
        return notif

    async def get_unread_count(self, user_id: int) -> int:
        result = await self.db.execute(
            select(func.count()).where(Notification.user_id == user_id, Notification.is_read == False)
        )
        return result.scalar_one()
