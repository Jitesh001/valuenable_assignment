from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .domain import ValidationError as DomainValidationError
from .repositories import PolicyTypeRepository, PolicyQuoteRepository
from .serializers import (
    IllustrationRequestSerializer,
    PolicyQuoteSerializer,
    PolicyTypeSerializer,
)
from .services import (
    IllustrationCommand,
    IllustrationService,
    PolicyTypeNotFound,
)


class PolicyTypeListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = PolicyTypeSerializer

    def get_queryset(self):
        return PolicyTypeRepository.list_active()


class CalculateView(APIView):
    """
    POST /api/policies/calculate/
    Single-policy benefit illustration. Stateless; honours `Idempotency-Key` header.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = IllustrationRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        idem_key = request.headers.get("Idempotency-Key")
        cmd = IllustrationCommand(
            user_id=request.user.id,
            policy_type_code=serializer.validated_data["policy_type"],
            domain_input=serializer.to_domain(),
            idempotency_key=idem_key,
            persist=True,
        )

        try:
            result = IllustrationService().illustrate(cmd)
        except PolicyTypeNotFound:
            return Response(
                {"detail": "Unknown policy_type."},
                status=status.HTTP_404_NOT_FOUND,
            )
        except DomainValidationError as exc:
            return Response(
                {"detail": "Validation failed.", "errors": exc.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            PolicyQuoteSerializer(result).data,
            status=status.HTTP_201_CREATED,
        )


class IllustrationView(APIView):
    """
    POST /api/policies/illustrate/
    Stateless calculator that DOESN'T persist. Useful for live what-if previews
    on the frontend without filling the DB with throwaway rows.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = IllustrationRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        cmd = IllustrationCommand(
            user_id=request.user.id,
            policy_type_code=serializer.validated_data["policy_type"],
            domain_input=serializer.to_domain(),
            persist=False,
        )

        try:
            result = IllustrationService().illustrate(cmd)
        except PolicyTypeNotFound:
            return Response(
                {"detail": "Unknown policy_type."},
                status=status.HTTP_404_NOT_FOUND,
            )
        except DomainValidationError as exc:
            return Response(
                {"detail": "Validation failed.", "errors": exc.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(result, status=status.HTTP_200_OK)


class QuoteHistoryView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = PolicyQuoteSerializer

    def get_queryset(self):
        return PolicyQuoteRepository.for_user(self.request.user.id)


class QuoteDetailView(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = PolicyQuoteSerializer

    def get_queryset(self):
        return PolicyQuoteRepository.for_user(self.request.user.id)
