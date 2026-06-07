import asyncio
from sqlalchemy import text
from src.db.session import async_session_maker
from src.db.models.identity import User
from src.db.models.enums import Role
from src.db.models.passes import PassType
from src.security import pwd_context


async def seed_db():
    print("Starting database seeding...")
    async with async_session_maker() as session:
        # Clear existing test users to prevent unique constraint errors
        print("Clearing existing test users...")
        await session.execute(
            text("DELETE FROM users WHERE email IN ('test_student@example.com', 'test_guard@example.com', 'test_warden@example.com', 'test_faculty@example.com')")
        )
        await session.commit()
        
        # Hash the shared test password once
        hashed_pw = pwd_context.hash("password123")

        print("Inserting test users...")
        test_student = User(
            email="test_student@example.com",
            name="test_student",
            hashed_password=hashed_pw,
            role=Role.STUDENT,
            is_active=True
        )
        
        test_guard = User(
            email="test_guard@example.com",
            name="test_guard",
            hashed_password=hashed_pw,
            role=Role.GUARD,
            is_active=True
        )

        test_warden = User(
            email="test_warden@example.com",
            name="Hostel Warden",
            hashed_password=hashed_pw,
            role=Role.WARDEN,
            is_active=True
        )

        test_faculty = User(
            email="test_faculty@example.com",
            name="Test Faculty",
            hashed_password=hashed_pw,
            role=Role.FACULTY,
            is_active=True
        )
        
        session.add_all([test_student, test_guard, test_warden, test_faculty])
        
        print("Inserting pass types...")
        # Clear existing pass types
        await session.execute(
            text("DELETE FROM pass_types WHERE name IN ('DAY_PASS', 'OUTSTATION', 'VACATION', 'VEHICLE')")
        )
        
        # Add basic pass types
        pass_types = [
            PassType(name="DAY_PASS", requires_approval=False),
            PassType(name="OUTSTATION", requires_approval=True),
            PassType(name="VACATION", requires_approval=True),
            PassType(name="VEHICLE", requires_approval=True)
        ]
        session.add_all(pass_types)
        
        await session.commit()
        
        print("Database seeded successfully with test users and pass types.")

if __name__ == "__main__":
    asyncio.run(seed_db())
