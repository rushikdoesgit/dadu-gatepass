import enum

class PassCategory(str, enum.Enum):
    DAY_PASS = "DAY_PASS"
    OUTSTATION = "OUTSTATION"
    VACATION = "VACATION"

class PassStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    USED = "USED"

class ResidencyStatus(str, enum.Enum):
    ON_CAMPUS = "ON_CAMPUS"
    OFF_CAMPUS_COMMUTER = "OFF_CAMPUS_COMMUTER"
    LONG_TERM_AWAY = "LONG_TERM_AWAY"

class StudentTier(str, enum.Enum):
    UNDERGRAD = "UNDERGRAD"
    POSTGRAD = "POSTGRAD"
    PHD = "PHD"

class Role(str, enum.Enum):
    STUDENT = "STUDENT"
    FACULTY = "FACULTY"
    VISITOR = "VISITOR"
    GUARD = "GUARD"
    SUPERVISOR = "SUPERVISOR"
    WARDEN = "WARDEN"
