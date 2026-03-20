from rest_framework.pagination import PageNumberPagination


class KonisPagination(PageNumberPagination):
    """
    Pagination standard KONIS.

    Paramètres GET :
      ?page=2            → page 2
      ?page_size=100     → 100 éléments par page (max 200)

    Réponse :
      {
        "count":    <int>,       # total d'objets
        "next":     <url|null>,  # page suivante
        "previous": <url|null>,  # page précédente
        "results":  [...]        # objets de la page courante
      }
    """
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200
    page_query_param = "page"
