from distutils.core import setup
setup(
    author='J Samuels',
    author_email='jeep123samuels@gmail.com',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'Topic :: Software Development :: Build Tools',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
    ],
    description='Base class for serializing data using pydantic Flask',
    download_url=(
        'https://github.com/Jeep123Samuels/'
        'pydantic_sql_orm_extension/archive/main.zip'
    ),
    keywords=['Flask', 'pydantic', 'serializers', 'sql'],
    license='MIT',
    name='pydantic_sql_orm_extension',
    packages=[
        'pydantic_sql_orm_extension',
    ],
    version='1.1.0',
    url='https://github.com/Jeep123Samuels/pydantic_sql_orm_extension',

    install_requires=[
        'Flask',
        'flask-openapi3',
        'Flask-SQLAlchemy',
        'pydantic',
        'SQLAlchemy',
    ]
)
