from django.shortcuts import render, redirect
from django.urls import reverse_lazy
from django.views.generic import ListView, DetailView, CreateView
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.mixins import LoginRequiredMixin
from .models import Ad
from .forms import AdForm
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from .models import Favorite
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db.models import Avg
from .models import Review
from .forms import ReviewForm
from django.contrib.auth.models import User



@login_required
def toggle_favorite(request, pk):
    ad = get_object_or_404(Ad, pk=pk)
    favorite, created = Favorite.objects.get_or_create(user=request.user, ad=ad)
    if not created:
        favorite.delete()
        status = 'removed'
    else:
        status = 'added'
    return JsonResponse({'status': status, 'is_favorite': created})

def register(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('login')
    else:
        form = UserCreationForm()
    return render(request, 'registration/register.html', {'form': form})

from .filters import AdFilter

class AdListView(ListView):
    model = Ad
    template_name = 'ads/ad_list.html'
    context_object_name = 'ads'
    paginate_by = 10

    def get_queryset(self):
        queryset = Ad.objects.filter(is_active=True)
        self.filterset = AdFilter(self.request.GET, queryset=queryset)
        return self.filterset.qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filter'] = self.filterset
        return context

from django.views.generic.edit import FormMixin
from .forms import ResponseForm

class AdDetailView(FormMixin, DetailView):
    model = Ad
    template_name = 'ads/ad_detail.html'
    context_object_name = 'ad'
    form_class = ResponseForm

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        ad = self.get_object()
        # Исключаем текущее объявление, берём 4 случайных активных
        context['recommended_ads'] = Ad.objects.filter(is_active=True).exclude(pk=ad.pk).order_by('?')[:4]
        return context

    def get_success_url(self):
        return reverse_lazy('ads:ad_detail', kwargs={'pk': self.object.pk})

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        form = self.get_form()
        if form.is_valid():
            return self.form_valid(form)
        else:
            return self.form_invalid(form)

    def form_valid(self, form):
        form.instance.ad = self.object
        form.instance.user = self.request.user
        form.save()
        return super().form_valid(form)

class AdCreateView(LoginRequiredMixin, CreateView):
    model = Ad
    form_class = AdForm
    template_name = 'ads/ad_form.html'
    success_url = reverse_lazy('ads:ad_list')

    def form_valid(self, form):
        form.instance.author = self.request.user
        return super().form_valid(form)

class FavoriteListView(LoginRequiredMixin, ListView):
    model = Favorite
    template_name = 'ads/favorite_list.html'
    context_object_name = 'favorites'

    def get_queryset(self):
        return Favorite.objects.filter(user=self.request.user).select_related('ad')

class MyAdsListView(LoginRequiredMixin, ListView):
    template_name = 'ads/my_ads.html'
    context_object_name = 'ads'

    def get_queryset(self):
        return Ad.objects.filter(author=self.request.user).prefetch_related('responses')

from django.urls import reverse_lazy
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin

class AdUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = Ad
    form_class = AdForm
    template_name = 'ads/ad_form.html'

    def test_func(self):
        ad = self.get_object()
        return self.request.user == ad.author

    def get_success_url(self):
        return reverse_lazy('ads:my_ads')

class AdDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    model = Ad
    template_name = 'ads/ad_confirm_delete.html'
    success_url = reverse_lazy('ads:my_ads')

    def test_func(self):
        ad = self.get_object()
        return self.request.user == ad.author

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect
from .models import Response

@login_required
def accept_response(request, pk):
    response = get_object_or_404(Response, pk=pk)
    # Проверяем, что текущий пользователь — автор объявления
    if request.user == response.ad.author:
        response.is_accepted = True
        response.save()
    return redirect('ads:my_ads')

@login_required
def decline_response(request, pk):
    response = get_object_or_404(Response, pk=pk)
    if request.user == response.ad.author:
        response.delete()
    return redirect('ads:my_ads')

# Добавьте эти импорты в начало файла, если их ещё нет:
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from .models import Response
from .forms import ReplyForm

# Сама функция
@login_required
def reply_to_response(request, pk):
    response = get_object_or_404(Response, pk=pk)
    # Проверка, что пользователь – автор объявления
    if request.user != response.ad.author:
        return redirect('ads:my_ads')

    if request.method == 'POST':
        form = ReplyForm(request.POST, instance=response)
        if form.is_valid():
            form.save()
            return redirect('ads:my_ads')
    else:
        form = ReplyForm(instance=response)

    return render(request, 'ads/reply_form.html', {
        'form': form,
        'response': response
    })

class UserProfileView(DetailView):
    model = User
    template_name = 'ads/user_profile.html'
    context_object_name = 'profile_user'

    def get_object(self):
        return get_object_or_404(User, username=self.kwargs['username'])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.get_object()
        context['ads'] = Ad.objects.filter(author=user, is_active=True)
        context['reviews'] = Review.objects.filter(to_user=user).select_related('from_user')
        context['avg_rating'] = context['reviews'].aggregate(Avg('rating'))['rating__avg']
        context['review_form'] = ReviewForm()
        # Можно ли текущему пользователю оставить отзыв?
        if self.request.user.is_authenticated and self.request.user != user:
            context['can_review'] = not Review.objects.filter(to_user=user, from_user=self.request.user).exists()
        else:
            context['can_review'] = False
        return context


@login_required
def add_review(request, username):
    to_user = get_object_or_404(User, username=username)
    if request.user == to_user:
        return redirect('ads:user_profile', username=username)  # самому себе нельзя
    if Review.objects.filter(to_user=to_user, from_user=request.user).exists():
        return redirect('ads:user_profile', username=username)  # уже оставлял
    if request.method == 'POST':
        form = ReviewForm(request.POST)
        if form.is_valid():
            review = form.save(commit=False)
            review.to_user = to_user
            review.from_user = request.user
            review.save()
            return redirect('ads:user_profile', username=username)
    else:
        form = ReviewForm()
    return render(request, 'ads/add_review.html', {'form': form, 'to_user': to_user})