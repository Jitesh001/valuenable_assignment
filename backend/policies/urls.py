from django.urls import path

from .views import (
    CalculateView,
    IllustrationView,
    PolicyTypeListView,
    QuoteDetailView,
    QuoteHistoryView,
)

urlpatterns = [
    path("types/", PolicyTypeListView.as_view(), name="policy-types"),
    path("calculate/", CalculateView.as_view(), name="policy-calculate"),
    path("illustrate/", IllustrationView.as_view(), name="policy-illustrate"),
    path("quotes/", QuoteHistoryView.as_view(), name="policy-quote-history"),
    path("quotes/<int:pk>/", QuoteDetailView.as_view(), name="policy-quote-detail"),
]
