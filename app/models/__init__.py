from app.models.person import Person
from app.models.event_type import EventType
from app.models.event_subtype import EventSubtype
from app.models.person_event import PersonEvent
from app.models.reference_book import Rank, Position
from app.models.person_positions import PersonPosition
"""Central registry of SQLAlchemy models.

Import this module before calling ``Base.metadata.create_all()`` so every
model is registered in SQLAlchemy metadata.
"""

from app.models.person_identity import Passport, PersonName
from app.models.person_military_service import PersonRank, PersonServiceHistory 

__all__ = [
    "EventSubtype",
    "EventType",
    "Passport",
    "Person",
    "PersonEvent",
    "PersonName",
    "PersonRank",
    "PersonServiceHistory",
    "Rank",
    "Position",
    "PersonPosition", "StaffStructure", "StaffVersion", "PersonAssignment",
    
]

from app.models.staff import StaffStructure, StaffVersion, PersonAssignment
from app.models.name_cases import NameDictionary, PersonNameCases, NameDictionaryImport
__all__ += ["NameDictionary", "PersonNameCases", "NameDictionaryImport"]

from app.models.geography import GeoUnit, GeoAlias, PersonBirthplace, PersonAddress
__all__ += ["GeoUnit", "GeoAlias", "PersonBirthplace", "PersonAddress"]
from app.models.geography_import import GeoSource, GeoImportLink, GeoCityDistrict
__all__ += ['GeoSource', 'GeoImportLink', 'GeoCityDistrict']
from app.models.person_contact import PersonContact
__all__ += ['PersonContact']
from app.models.mirage import PersonPositionMirage
__all__ += ['PersonPositionMirage']
from app.models.service_basis import PersonServiceBasis, TccOffice, TccImport
__all__ += ['PersonServiceBasis', 'TccOffice', 'TccImport']
from app.models.accounts import User, UserSession
from app.models.documents import DocumentType, PersonDocumentState, PersonDocument, DocumentDetails, DrivingCategory, DocumentFile, DocumentAudit
__all__ += ['User', 'UserSession', 'DocumentType', 'PersonDocumentState', 'PersonDocument', 'DocumentDetails', 'DrivingCategory', 'DocumentFile', 'DocumentAudit']
from app.models.medical import MedicalExam, Injury, Award, DnaSample, PersonnelTask, MedicalSelection, MedicalDocumentLink, PersonnelAudit
__all__ += ['MedicalExam','Injury','Award','DnaSample','PersonnelTask','MedicalSelection','MedicalDocumentLink','PersonnelAudit']
