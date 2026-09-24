from enum import StrEnum


class DataClass(StrEnum):
    OPERATIONAL = 'OPERATIONAL'
    STRUCTURED_INTELLIGENCE = 'STRUCTURED_INTELLIGENCE'
    ANALYTICAL = 'ANALYTICAL'
    CACHE = 'CACHE'
    ARCHIVE = 'ARCHIVE'


class StorageRouter:
    def handoff_owner(self, classification: str):
        kind={'HANDOFF_RAW':DataClass.ARCHIVE,'STRUCTURED_INTELLIGENCE':DataClass.STRUCTURED_INTELLIGENCE,
              'WEB_PRESENTATION_CACHE':DataClass.CACHE,'ANALYTICAL_DERIVED':DataClass.ANALYTICAL}[classification]
        return self.route(kind)

    def route(self, kind: DataClass):
        if not isinstance(kind, DataClass):
            raise TypeError('Typed classification required')
        return {DataClass.OPERATIONAL: 'mariadb', DataClass.STRUCTURED_INTELLIGENCE: 'sqlserver',
                DataClass.ANALYTICAL: 'future_parquet', DataClass.CACHE: 'mariadb',
                DataClass.ARCHIVE: 'filesystem'}[kind]

    def classify(self, object_type: str):
        return {'job': DataClass.OPERATIONAL, 'observation': DataClass.STRUCTURED_INTELLIGENCE,
                'fixture': DataClass.STRUCTURED_INTELLIGENCE, 'odds': DataClass.STRUCTURED_INTELLIGENCE,
                'features': DataClass.ANALYTICAL, 'summary': DataClass.CACHE,
                'raw_capture': DataClass.ARCHIVE}[object_type]
