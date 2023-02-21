from copy import deepcopy

from pydantic import BaseModel
from sqlalchemy import desc, func


class BaseCrud(BaseModel):
    """
    __model_kls__: Define the main postgres model to be used for the orm.
    __related_kls__: retrieve information if any related data needs
                  to be created.
                  Eg. one_to_one=dict(<field_in_main_schema>=<Postgres_Model>)

        Example:
        class SomeSerializer(BaseCrud):
            __model_kls__ = SomeModel
            __related_kls__ = {
                "one_to_many": {
                    "<field_defined_in_some_model>": {
                        "model_kls": TheClassRelated,
                        "linked_field": "field_defined_in_some_model_id",
                    },
                }
                "many_to_many": {
                    "<field_defined_in_some_model>": {
                        "model_kls": TheClassRelated,
                        "second_kls": TheLinkTableBetweenTheRelatonTables,
                        "linked_field": [
                            "the_primary_model_id", "the_related_id",
                        ],
                    },
                }
            }
    """
    __db_session__ = None
    __by_alias_global__: bool = False
    __model_kls__ = None
    __related_kls__: dict = dict(
        one_to_one=dict(),
        one_to_many=dict(),
        many_to_many=dict(),
    )
    __serialize_when_none__: bool = False
    
    def _create(self, model_kls, kwargs: dict):
        """Given model class create data."""
        session = self.__db_session__()
        
        instance = model_kls(**kwargs)
        session.add(instance)
        session.commit()
        return instance
    
    def _get_one(self, model_kls, kwargs: dict):
        """Given model class and parameters fetch data from db."""
        return self.__db_session__().query(model_kls).filter_by(
            **kwargs).first()
    
    def _get_many(self, model_kls, kwarg_list):
        """Assume list of kwargs need to be equal to column value."""
        objs: list = list()
        session = self.__db_session__()
        for kwarg in kwarg_list:
            objs.extend(session.query(model_kls).filter_by(**kwarg).all())
        return objs

    def _get_or_create_many(
        self, model_kls, kwargs_list: list, return_ids=True
    ):
        """Given model class create many data."""
        # Restructure list in dict with keys as index
        if not kwargs_list:
            return []
        
        ids_to_return: list = list()
        create_list: list = list()
        get_objects: list = self._get_many(model_kls, kwargs_list)
        keys: list = list(kwargs_list[0].keys())

        if not get_objects:
            create_list = kwargs_list
        else:
            for kwarg in kwargs_list:
                already_created = False
                for obj in get_objects:
                    if all([
                        kwarg[key_] == getattr(obj, key_)
                        for key_ in keys
                    ]):
                        already_created = True
                        break

                if not already_created:
                    create_list.append(kwarg)

        session = self.__db_session__()
        if create_list:
            session.bulk_insert_mappings(model_kls, create_list)
            session.commit()
            get_objects: list = self._get_many(model_kls, kwargs_list)

        if not return_ids:
            return get_objects

        for obj in get_objects:
            ids_to_return.append(obj.id)
        return ids_to_return
    
    def _update_many_to_many(self, sub_kls, kwargs, obj, rel_field):
        session = self.__db_session__()
        setattr(obj, rel_field, [])
        session.add(obj)
        session.commit()

        list_objs = self._get_or_create_many(sub_kls, kwargs, False)

        setattr(obj, rel_field, list_objs)
        session.add(obj)
        session.commit()
        return obj
    
    def _get_targeted_columns(self, columns_, session):
        q = session.query(self.__model_kls__)
        # Caters to get specific columns and not the whole row.
        if columns_ and isinstance(columns_, (list, tuple,), ):
            columns = [getattr(self.__model_kls__, c) for c in columns_]
            q = session.query(*columns)
        return q

    def _get_validated_data(self):
        pydantic_kw: dict = dict(exclude_unset=True)
        if self.__serialize_when_none__:
            pydantic_kw.update(dict(exclude_none=False, exclude_unset=False))
        if self.__by_alias_global__:
            pydantic_kw.update(dict(by_alias=True))
        return self.dict(**pydantic_kw)

    def bulk_save(self):
        pass

    def update(self, filter_fields, **kwargs):
        """Provide fields/data to target the correct obj, preferable
        the id of obj.

        This update version can only handle 1-level deep updates.
        """
        # Need to handle if error occurs

        validated_data = self._get_validated_data()
        hold_data = deepcopy(validated_data)
        session = self.__db_session__()
        obj = session.query(self.__model_kls__).filter_by(**filter_fields).one()

        if not obj:
            return

        if "id" in validated_data:
            del validated_data["id"]

        one_to_one = self.__related_kls__.get("one_to_one", dict())
        one_to_many = self.__related_kls__.get("one_to_many", dict())
        many_to_many = self.__related_kls__.get("many_to_many", dict())

        # Handle updates targeting one-to-one or one-to-many
        for k, v in validated_data.items():
            def update_process(ctx):
                del hold_data[k]
                target_obj = getattr(obj, k)
                target_obj = target_obj.to_json(
                    rel=False) if target_obj else dict()

                linked_field = ctx["linked_field"]
                linked_model = ctx["model_kls"]
                # Related object does not exist, create
                if "id" not in target_obj:
                    target_obj.update(validated_data[k])
                    rel_obj = self._create(linked_model, target_obj)
                    setattr(obj, linked_field, rel_obj.id)

                elif "id" in target_obj:
                    rel_obj = self._get_one(
                        linked_model, 
                        dict(id=target_obj["id"])
                    )
                    for k_, v_ in validated_data[k].items():
                        setattr(rel_obj, k_, v_)
                    session.add(rel_obj)

            if isinstance(v, dict) and (k in one_to_many or k in one_to_one):
                update_process(one_to_many.get(k) or one_to_one.get(k))

            elif isinstance(v, list) and k in many_to_many:
                obj = self._update_many_to_many(
                    sub_kls=many_to_many[k]["model_kls"],
                    obj=obj,
                    kwargs=v,
                    rel_field=k,
                )
                del hold_data[k]

        for k, v in hold_data.items():
            if not isinstance(v, (dict, list, tuple,)):
                setattr(obj, k, v)

        session.add(obj)
        session.commit()

        return self._return_results(obj, **kwargs)

    def create(self, **kwargs):
        """Create new row under target model."""

        # Need to handle if error occurs
        validated_data = self._get_validated_data()
        if not validated_data:
            return None

        if "id" in validated_data:
            del validated_data["id"]

        session = self.__db_session__()

        one_to_one = self.__related_kls__.get("one_to_one", dict())
        one_to_many = self.__related_kls__.get("one_to_many", dict())
        many_to_many = self.__related_kls__.get("many_to_many", dict())

        one_to_one_data = dict()
        for related_field in one_to_one.keys():
            if validated_data.get(related_field):
                one_to_one_data[related_field] = validated_data[related_field]
                del validated_data[related_field]

        for related_field, val in one_to_many.items():
            if validated_data.get(related_field):
                data_ = validated_data[related_field]

                # Remove data from main parent data
                del validated_data[related_field]

                # Get or create the new object
                rel_model = val["model_kls"]
                rel_instance = session.query(rel_model).filter_by(
                    **data_).first()
                if not rel_instance:
                    rel_instance = rel_model(**data_)
                    session.add(rel_instance)
                    session.commit()
                # Link created rel_obj back to parent
                validated_data[val["linked_field"]] = rel_instance.id

        # Many-to-many should always be an input of lists of dictionaries.
        # The serializer will have a main_model and secondary model.
        # Also a linked_fields-list that is the
        # two fields defined on the secondary model.
        many_to_many_link: list = list()
        for related_field, val in many_to_many.items():
            if validated_data.get(related_field):
                data_ = validated_data[related_field]

                # Remove data from main parent data
                del validated_data[related_field]

                # Get or create the new object
                rel_model = val["model_kls"]

                # Here we loop through each dictionary in the list.
                # each object is created, id stored,
                # and then other linked field hold.
                for v in data_:

                    # Check first if exist.
                    rel_instance = session.query(rel_model).filter_by(
                        **v).first()
                    if not rel_instance:
                        rel_instance = rel_model(**v)
                        session.add(rel_instance)
                        session.commit()

                    # Get the two linked fields on defined on secondary model
                    first_field = val["linked_fields"][0]
                    second_field = val["linked_fields"][-1]
                    # Remember the one field later
                    # populated after main object created.
                    many_to_many_link.append(
                        {
                            "first_field": first_field,
                            second_field: rel_instance.id,
                            "model": val["second_kls"],
                        }
                    )

        # Main/Parent object created.
        obj_created = self.__model_kls__(**validated_data)
        # Need to commit at this point, some other related might need it.
        session.add(obj_created)

        session.commit()

        # One-to-one
        for field_, data in one_to_one_data.items():
            model_ = one_to_one[field_]["model_kls"]
            link_field = one_to_one[field_]["linked_field"]

            data[link_field] = obj_created.id
            instance = model_(**data)
            session.add(instance)

        # Many to Many
        for linked_data in many_to_many_link:
            field_ = linked_data["first_field"]
            link_model = linked_data["model"]

            del linked_data["first_field"]
            del linked_data["model"]

            linked_data[field_] = obj_created.id
            instance = link_model(**linked_data)
            session.add(instance)

        session.commit()
        return self._return_results(obj_created, **kwargs)

    def get_or_create(self, **kwargs):
        if not self.__model_kls__:
            return {}
        obj = self.get_obj(**kwargs)

        if obj:
            return obj

        return self.create(**kwargs)

    def get_obj(self, **kwargs):
        """
        columns: A list of columns to pull from database and not getting
                the whole row.
                It's preferred to always include the id with the columns.
                E.g: ["id", "columns1", "columns2"]
        """
        if not self.__model_kls__:
            return {}

        session = self.__db_session__()

        data = self._get_validated_data()
        if not data:
            return None

        q = self._get_targeted_columns(kwargs.get("columns"), session)

        if data.get("id"):
            obj = q.filter_by(id=data.get("id")).first()
            return self._return_results(obj, **kwargs)

        # Remove any weird objects in the query set
        # Needs to be flat variables.
        data_ = deepcopy(data)
        for k, v in data.items():
            if isinstance(v, (tuple, list, dict)):
                del data_[k]

        obj = q.filter_by(**data_).first()

        return self._return_results(obj, **kwargs)

    def get_obj_by_order(self, order_by: dict, **kwargs):
        """
        Given model class and parameters fetch data from db.
        order_by = {desc: True/False, field: name of field to order_by}
        columns: A list of columns to pull from database and not getting the
                whole row.
                It's preferred to always include the id with the columns.
                E.g: ["id", "columns1", "columns2"]
        """
        session = self.__db_session__()

        data = self._get_validated_data()
        data_ = deepcopy(data)
        for k, v in data.items():
            if isinstance(v, (tuple, list, dict)):
                del data_[k]

        q = self._get_targeted_columns(kwargs.get("columns"), session)

        q = q.filter_by(**data_)

        if order_by.get("desc"):
            obj = q.order_by(desc(order_by["field"])).first()
        else:
            obj = q.order_by(order_by["field"]).first()

        return self._return_results(obj, **kwargs)

    def get_objects(self, **kwargs):
        """
        columns: A list of columns to pull from database and not getting the
                whole row.
                It's preferred to always include the id with the columns.
                E.g: ["id", "columns1", "columns2"]
        count: A boolean that will count the matching rows in db.
                count overrules any other parameters.
        """
        # TODO: need to add support for order_by
        data = self._get_validated_data()
        session = self.__db_session__()

        if kwargs.get("count") is True:
            results = session.query(
                func.count(self.__model_kls__.id)).filter_by(**data).one()[0]
            return results[0] if results else 0

        q = self._get_targeted_columns(kwargs.get("columns"), session)
        # if kwargs.get("get_in") is True:
        #     results = session.query(model_).filter_by(**data).all()
        #     .filter(~model_.ctrl_id.in_(all_insured_ctrl_ids))
        #     return results[0] if results else 0
        results = q.filter_by(**data).all()
        return self._return_results(results, **kwargs)

    def hard_delete(self):
        session = self.__db_session__()

        data = self._get_validated_data()
        if not data:
            return None

        if data.get("id"):
            session.query(self.__model_kls__).filter_by(id=data["id"]).delete()
            session.commit()
            return

        data_ = deepcopy(data)
        for k, v in data.items():
            if isinstance(v, (tuple, list, dict)):
                del data_[k]

        obj = session.query(self.__model_kls__).filter_by(**data_).first()
        if obj:
            session.delete(obj)
            session.commit()

    def hard_delete_objects(self):
        session = self.__db_session__()

        data = self._get_validated_data()
        if not data:
            return None

        data_ = deepcopy(data)
        for k, v in data.items():
            if isinstance(v, (tuple, list, dict)):
                del data_[k]

        session.query(self.__model_kls__).filter_by(**data_).delete()
        session.commit()

    @staticmethod
    def _return_results(results, **kwargs):
        if not results:
            return results

        _include_hybrid = kwargs.get("_include_hybrid", False)
        _rel = kwargs.get("_rel", False)
        _return_dict = kwargs.get("_return_dict", True)
        if not _return_dict:
            return results

        if isinstance(results, list) and not kwargs.get("columns"):
            return [
                result.to_json(include_hybrid=_include_hybrid, rel=_rel)
                for result in results
            ]
        elif kwargs.get("columns"):
            if isinstance(results, list):
                return [
                    dict(zip(kwargs.get("columns"), result))
                    for result in results
                ]
            # Looses the relationship data pull if columns is specified
            return dict(zip(kwargs.get("columns"), results))

        return results.to_json(include_hybrid=_include_hybrid, rel=_rel)
