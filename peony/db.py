from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.event import listen
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import Column, Integer, String, Date
from sqlalchemy.sql import select, func
from geoalchemy2 import Geometry, functions
from geoalchemy2.shape import to_shape
from peony.utils import geojson_to_wktelement
import datetime
import pathlib
from os.path import exists

Base = declarative_base()

class Image(Base):
    """A class representing a single piece of satellite data.
    """
    __tablename__ = 'image'
    id = Column(Integer, primary_key=True)
    path = Column(String)
    name = Column(String)
    geom = Column(Geometry('POLYGON', management=True))
    date = Column(Date)

def load_spatialite(dbapi_conn, connection_record):
    dbapi_conn.enable_load_extension(True)
    dbapi_conn.load_extension('mod_spatialite')

def init_spatial_metadata(engine):
    conn = engine.connect()
    conn.execute(select([func.InitSpatialMetaData()]))
    conn.close()

def csv_2_spatialite(csv_path, sqlite_path):
    """Populates a spatialite database based on a CSV file.

    Parameters
    ----------
    csv_path: str
        A path to a CSV file with no header and 4 columns.
        The columns are in this order: date, polygon coordinates, 
        name and path.
    sqlite_path: str
        Path to where a spatialite database will be stored.
    """
    engine = create_engine(f"sqlite:///{sqlite_path}")
    listen(engine, 'connect', load_spatialite)
    init_spatial_metadata(engine)
    Image.__table__.create(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    counter = 0
    with open(csv_path, 'r') as fd:
        for line in fd:
            line = line.strip().split(',')
            date_str = line[0].strip('"').split('.')[0]
            date = datetime.datetime.strptime(date_str, '%Y-%m-%dT%H:%M:%S')
            polygon = line[1].strip('"').strip().split(' ')
            assert(len(polygon) % 2 == 0)
            assert(polygon[0] == polygon[-2])
            assert(polygon[1] == polygon[-1])
            polygon = ', '.join([polygon[i] + ' ' + polygon[i + 1] for i in range(len(polygon) // 2)])
            polygon = f"POLYGON(({polygon}))"
            name = line[2].strip('"').strip()
            path = pathlib.PurePath(line[3].strip('"').strip()).parent
            session.add(Image(path=str(path), geom=polygon, name=name, date=date))
            counter += 1
            if (counter % 1000) == 0:
                session.commit()
    session.commit()

def query_polygon(sqlite_path, geojson_path):
    """Will try to find records whos geometry overlaps with the given polygon.

    Parameters
    ----------
    sqlite_path: str
        A path to the sqlite database that contains satellite image metadata.
    geojson_path: str
        A path to a GeoJSON file that contains the polygon to query by.

    Returns
    -------
    list
        A list with pairs consisting of path and product name.
    """
    assert(exists(sqlite_path))
    assert(exists(geojson_path))
    engine = create_engine(f"sqlite:///{sqlite_path}")
    listen(engine, 'connect', load_spatialite)
    Session = sessionmaker(bind=engine)
    session = Session()
    polygon = geojson_to_wktelement(geojson_path)
    query = session.query(Image).filter(Image.geom != None).filter(
        Image.geom.ST_Overlaps(polygon))
    return [(image.path, image.name) for image in query]
