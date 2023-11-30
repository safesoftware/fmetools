"""
This module defines the API for the Scripted Selection GUI element.
A Scripted Selection provides choices that may be presented in a tree structure.
Each choice has a display name and an ID.
This GUI element is typically used to present choices that:

- Originate from an external API
- Vary depending on the value of other parameters
- Have a hierarchy, such as files and folders
- Have a user-facing display name and an internal ID that's very different
- Have IDs that are not meaningful to the user, such as GUIDs

A Scripted Selection is composed of two parts:

- An implementation of :class:`ScriptedSelectionCallback`
- A Scripted Selection GUI element definition,
  which includes a reference to the :class:`ScriptedSelectionCallback` implementation above,
  and other configuration, such as Input Parameters, search support, and more.
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class Item(dict):
    """
    An Item is a selectable element in a Scripted Selection.
    Containers are a type of Item that may contain other Items.
    Every Item has an ID, a display name, and a flag for whether it represents a container.
    """

    def __init__(self, id: str, name: str, is_container: bool):
        super().__init__()
        self.id = id
        self.name = name
        self.is_container = is_container

    @property
    def is_container(self) -> bool:
        """
        If true, then this Item represents a container.
        """
        return self["IS_CONTAINER"]

    @is_container.setter
    def is_container(self, value: bool) -> None:
        self["IS_CONTAINER"] = value

    @property
    def id(self) -> str:
        """
        A value that uniquely identifies this Item.
        """
        return self["ID"]

    @id.setter
    def id(self, value: str) -> None:
        self["ID"] = value

    @property
    def name(self) -> str:
        """
        The display name for this Item.
        """
        return self["NAME"]

    @name.setter
    def name(self, value: str) -> None:
        self["NAME"] = value


class PaginationInfo(dict):
    """
    Holds the information needed to request the next page of results for a Scripted Selection.
    """

    def __init__(self, args: Dict[str, Any]):
        super().__init__()
        self.args = args

    @property
    def args(self) -> Dict[str, Any]:
        """
        Key-value pairs of arguments needed to get the next page of results.
        This is often an offset or a page token.
        """
        return self["ARGS"]

    @args.setter
    def args(self, value: Dict[str, Any]) -> None:
        self["ARGS"] = value


class ContainerContentResponse(dict):
    """
    Represents the return value of :meth:`ScriptedSelectionCallback.get_container_contents` that's expected by FME.
    """

    def __init__(
        self, contents: List[Item], continuation: Optional[PaginationInfo] = None
    ):
        super().__init__()
        self.contents = contents
        self.pagination = continuation

    @property
    def pagination(self) -> Optional[PaginationInfo]:
        """
        If there are more results to fetch, then this holds the arguments
        needed to request the next page of results.
        The arguments are added to the next call to :meth:`ScriptedSelectionCallback.get_container_contents`.
        """
        return self["CONTINUE"]

    @pagination.setter
    def pagination(self, value: Optional[PaginationInfo]) -> None:
        self["CONTINUE"] = value

    @property
    def contents(self) -> List[Item]:
        """
        List of Items in the container.
        """
        return self["CONTENTS"]

    @contents.setter
    def contents(self, value: List[Item]) -> None:
        self["CONTENTS"] = value


class ScriptedSelectionCallback(ABC):
    """
    Abstract base class representing the interface for Scripted Selection
    GUI element callbacks.

    Every Scripted Selection element must specify an implementation of this class.
    """

    def __init__(self, args: dict[str, Any]):
        """
        :param args: The names and values of the Input Parameters and Input Dictionary
            configured on the Scripted Selection GUI element.
        """
        raise NotImplementedError

    @abstractmethod
    def get_container_contents(
        self,
        *,
        container_id: Optional[str] = None,
        limit: Optional[int] = None,
        query: Optional[str] = None,
        **kwargs: dict[str, Any],
    ) -> ContainerContentResponse:
        """
        Get the Items in a given container.
        Returns direct children only. Must not return other descendants.

        :param container_id: Return the Items in the container with this ID.
            The root container may be represented by None, empty string, "/",
            or a default value defined by the implementation.
        :param limit: The maximum number of Items this method should return.
            If the number of Items in the container exceeds this limit,
            then pagination info should also be returned.
        :param query: A string to filter the results by.
            The implementation decides how to interpret the value.
            Only applicable if the Scripted Selection supports search and the user
            has provided input in the search field.
        :param kwargs: Additional arguments, including:

            - Input Parameters. Values may have changed from initialization.
            - Input Dictionary.
            - Pagination arguments if this is a request for the next page of results.
        :returns: A response that lists the container's direct children,
            with pagination arguments for the next page if applicable.
        """
        raise NotImplementedError
