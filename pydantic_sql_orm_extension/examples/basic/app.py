import sqlite3
import typing as t

from flask import current_app, g, make_response
from flask_openapi3 import OpenAPI, Tag
from flask_sqlalchemy import SQLAlchemy
from pydantic import BaseModel
from sqlalchemy.ext.declarative import declared_attr

from pydantic_sql_orm_extension.base import BaseCrud
from pydantic_sql_orm_extension.json_mixin import OutputMixin


app = OpenAPI(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///db.sqlite3'
app.config['SECRET_KEY'] = 'random string'

db = SQLAlchemy(app)

courses_tag = Tag(name='courses', description='Courses')
dorms_tag = Tag(name='dorms', description='Dorms')
student_tag = Tag(name='students', description='Students')


def connect_db():
    db_ = sqlite3.connect(
        current_app.config['SQLALCHEMY_DATABASE_URI'],
        detect_types=sqlite3.PARSE_DECLTYPES
    )
    db_.row_factory = sqlite3.Row
    return db_


def get_db():
    """Opens a new database connection if there is none yet for the
    current application context.
    """
    if not hasattr(g, 'sqlite_db'):
        g.sqlite_db = connect_db()
    return g.sqlite_db


@app.teardown_appcontext
def close_db(error):
    """Closes the database again at the end of the request."""
    if hasattr(g, 'sqlite_db'):
        g.sqlite_db.close()


@app.route('/')
def hello_world():
    return 'Hello, World!'


class IdGet(BaseModel):
    id: int


# -----------Models------------------


class StudentsCourses(OutputMixin, db.Model):
    __tablename__ = 'students_courses'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    @declared_attr
    def students_id(cls):
        return db.Column(db.Integer, db.ForeignKey('students.id'))

    @declared_attr
    def courses_id(cls):
        return db.Column(db.Integer, db.ForeignKey('courses.id'))


class Students(OutputMixin, db.Model):
    __table_name__ = 'students'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(100))
    is_admin = db.Column(db.Boolean())
    dorm_id = db.Column(db.Integer, db.ForeignKey('dorms.id'))
    courses = db.relationship(
        'Courses',
        secondary=StudentsCourses.__table__,
    )
    dorm = db.relationship('Dorms')


class Courses(OutputMixin, db.Model):
    __table_name__ = 'courses'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    faculty = db.Column(db.String(100))
    major = db.Column(db.String(100))


class Dorms(OutputMixin, db.Model):
    __table_name__ = 'dorms'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    all_students = db.relationship('Students')

# -----------Models------------------

# --------------------------------Courses--------------


class DormsBase(BaseCrud, BaseModel):
    __model_kls__ = Dorms
    __db_session__ = db.session


class DormsCreate(DormsBase):
    name: str


class DormsUpdate(DormsBase):
    name: t.Optional[str]


class DormsGet(DormsBase):
    name: t.Optional[str]


class DormsGetExtra(DormsGet):
    show_all_students: t.Optional[bool]

# --------------------------------Courses--------------


# --------------------------------Courses--------------


class CoursesBase(BaseCrud, BaseModel):
    __model_kls__ = Courses
    __db_session__ = db.session


class CoursesCreate(CoursesBase):
    name: str
    faculty: str
    major: str


class CoursesGet(CoursesBase):
    name: t.Optional[str]
    faculty: t.Optional[str]
    major: t.Optional[str]


class CoursesUpdate(CoursesBase):
    name: t.Optional[str]
    faculty: t.Optional[str]
    major: t.Optional[str]

# --------------------------------Courses--------------


# --------------------------------StudentBase--------------


class StudentBase(BaseCrud, BaseModel):
    __model_kls__ = Students
    __db_session__ = db.session
    __related_kls__: dict = {
        'one_to_many': {
            'dorm': {
                'model_kls': Dorms,
                'linked_field': 'dorm_id',
            },
        },
        'many_to_many': {
            'courses': {
                'model_kls': Courses,
                'second_kls': StudentsCourses,
                'linked_fields': ['students_id', 'courses_id'],
            },
        }
    }


class StudentCreate(StudentBase):
    name: str
    is_admin: bool
    dorm_id: t.Optional[int]
    dorm: t.Optional[DormsCreate]
    courses: t.Optional[t.List[CoursesCreate]]


class StudentUpdate(StudentBase):
    name: t.Optional[str]
    is_admin: t.Optional[bool]
    dorm_id: t.Optional[int]
    dorm: t.Optional[DormsUpdate]
    courses: t.Optional[CoursesUpdate]


class StudentGet(StudentBase):
    id: t.Optional[int]
    name: t.Optional[str]
    is_admin: t.Optional[bool]
    dorm_id: t.Optional[int]

# --------------------------------StudentBase--------------


@app.get('/students', tags=[student_tag])
def get_student(query: StudentGet):
    return make_response(
        query.get_objects(**dict(_rel=True)),
        200,
    )


@app.post('/students', tags=[student_tag])
def create_student(body: StudentCreate):
    return make_response(body.create(**dict(_rel=True)), 200)


@app.patch('/students/<int:student_id>', tags=[student_tag])
def update_student(path: IdGet, body: StudentUpdate):

    return make_response(
        body.update(filter_fields=path.dict(), **dict(_rel=True)),
        200,
    )


@app.get('/courses', tags=[courses_tag])
def get_course(query: CoursesGet):
    return make_response(query.get_objects(**dict(_rel=True)), 200)


@app.post('/courses', tags=[courses_tag])
def create_course(body: CoursesCreate):
    return make_response(body.create(**dict(_rel=True)), 200)


@app.get('/dorms', tags=[dorms_tag])
def get_dorm(query: DormsGet):
    return make_response(query.get_objects(), 200)


@app.get('/dorms/extra', tags=[dorms_tag])
def get_dorm_extra(query: DormsGetExtra):
    data = query.dict(exclude_unset=True)
    data.pop('show_all_students', None)
    return make_response(
        DormsGet(**data).get_objects(**dict(_rel=query.show_all_students)),
        200
    )


@app.post('/dorms', tags=[dorms_tag])
def create_dorm(body: DormsCreate):
    return make_response(body.create(**dict(_rel=True)), 200)


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)
