"""
Utilities related to API views
"""
import functools
from django.core.exceptions import NON_FIELD_ERRORS, ValidationError
from django.http import Http404
from django.utils.translation import ugettext as _

from rest_framework import status, response
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.mixins import RetrieveModelMixin, UpdateModelMixin
from rest_framework.generics import GenericAPIView

from lms.djangoapps.courseware.courses import get_course_with_access
from opaque_keys.edx.keys import CourseKey
from xmodule.modulestore.django import modulestore

from openedx.core.lib.api.authentication import (
    SessionAuthenticationAllowInactiveUser,
    OAuth2AuthenticationAllowInactiveUser,
)
from openedx.core.lib.api.permissions import IsUserInUrl, IsAuthenticatedOrDebug
from util.milestones_helpers import any_unfulfilled_milestones


class DeveloperErrorViewMixin(object):
    """
    A view mixin to handle common error cases other than validation failure
    (auth failure, method not allowed, etc.) by generating an error response
    conforming to our API conventions with a developer message.
    """
    def make_error_response(self, status_code, developer_message):
        """
        Build an error response with the given status code and developer_message
        """
        return Response({"developer_message": developer_message}, status=status_code)

    def make_validation_error_response(self, validation_error):
        """
        Build a 400 error response from the given ValidationError
        """
        if hasattr(validation_error, "message_dict"):
            response_obj = {}
            message_dict = dict(validation_error.message_dict)
            non_field_error_list = message_dict.pop(NON_FIELD_ERRORS, None)
            if non_field_error_list:
                response_obj["developer_message"] = non_field_error_list[0]
            if message_dict:
                response_obj["field_errors"] = {
                    field: {"developer_message": message_dict[field][0]}
                    for field in message_dict
                }
            return Response(response_obj, status=400)
        else:
            return self.make_error_response(400, validation_error.messages[0])

    def handle_exception(self, exc):
        if isinstance(exc, APIException):
            return self.make_error_response(exc.status_code, exc.detail)
        elif isinstance(exc, Http404):
            return self.make_error_response(404, "Not found.")
        elif isinstance(exc, ValidationError):
            return self.make_validation_error_response(exc)
        else:
            raise


def view_course_access(depth=0, access_action='load', check_for_milestones=False):
    """
    Method decorator for an API endpoint that verifies the user has access to the course.
    """
    def _decorator(func):
        """Outer method decorator."""
        @functools.wraps(func)
        def _wrapper(self, request, *args, **kwargs):
            """
            Expects kwargs to contain 'course_id'.
            Passes the course descriptor to the given decorated function.
            Raises 404 if access to course is disallowed.
            """
            course_id = CourseKey.from_string(kwargs.pop('course_id'))
            with modulestore().bulk_operations(course_id):
                try:
                    course = get_course_with_access(
                        request.user,
                        access_action,
                        course_id,
                        depth=depth
                    )
                except Http404:
                    # any_unfulfilled_milestones called a second time since has_access returns a bool
                    if check_for_milestones and any_unfulfilled_milestones(course_id, request.user.id):
                        message = {
                            "developer_message": "Cannot access content with unfulfilled "
                                                 "pre-requisites or unpassed entrance exam."
                        }
                        return response.Response(data=message, status=status.HTTP_204_NO_CONTENT)
                    else:
                        raise
                return func(self, request, course=course, *args, **kwargs)
        return _wrapper
    return _decorator


def view_auth_classes(is_user=False):
    """
    Function and class decorator that abstracts the authentication and permission checks for api views.
    """
    def _decorator(func_or_class):
        """
        Requires either OAuth2 or Session-based authentication.
        If is_user is True, also requires username in URL matches the request user.
        """
        func_or_class.authentication_classes = (
            OAuth2AuthenticationAllowInactiveUser,
            SessionAuthenticationAllowInactiveUser
        )
        func_or_class.permission_classes = (IsAuthenticatedOrDebug,)
        if is_user:
            func_or_class.permission_classes += (IsUserInUrl,)
        return func_or_class
    return _decorator


class RetrievePatchAPIView(RetrieveModelMixin, UpdateModelMixin, GenericAPIView):
    """
    Concrete view for retrieving and updating a model instance. Like DRF's RetriveUpdateAPIView, but without PUT.
    """
    def get(self, request, *args, **kwargs):
        """
        Retrieves the specified resource using the RetrieveModelMixin.
        """
        return self.retrieve(request, *args, **kwargs)

    def patch(self, request, *args, **kwargs):
        """
        Checks for validation errors, then updates the model using the UpdateModelMixin.
        """
        field_errors = self._validate_patch(request.DATA)
        if field_errors:
            return Response({'field_errors': field_errors}, status=status.HTTP_400_BAD_REQUEST)
        return self.partial_update(request, *args, **kwargs)

    def _validate_patch(self, patch):
        """
        Validates a JSON merge patch. Captures DRF serializer errors and converts them to edX's standard format.
        """
        field_errors = {}
        serializer = self.get_serializer(self.get_object_or_none(), data=patch, partial=True)
        fields = self.get_serializer().get_fields()  # pylint: disable=maybe-no-member

        for key in patch:
            if key not in fields:
                field_errors[key] = {
                    'developer_message': "This field is not present on this resource",
                    'user_message': _("This field is not present on this resource"),
                }
            elif fields[key].read_only:
                field_errors[key] = {
                    'developer_message': "This field is not editable",
                    'user_message': _("This field is not editable"),
                }

        if not serializer.is_valid():  # pylint: disable=maybe-no-member
            errors = serializer.errors  # pylint: disable=maybe-no-member
            for key, error in errors.iteritems():
                field_errors[key] = {
                    'developer_message': u"Value '{field_value}' is not valid for field '{field_name}': {error}".format(
                        field_value=patch[key], field_name=key, error=error
                    ),
                    'user_message': _(u"This value is invalid."),
                }

        return field_errors
