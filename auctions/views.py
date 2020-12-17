from django.contrib.auth import authenticate, login, logout
from django.db import IntegrityError
from django.db.models import Max
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django import forms
from django.contrib.auth.decorators import login_required
#from .models import *
from .models import User, Listing, Bid, Category, Comment, Watchlist

class NewListingForm(forms.ModelForm):
    class Meta:
        model=Listing
        fields=('title','description', 'starting_bid', 'image_url', 'categories')
        widgets = {
            'title': forms.TextInput(
                attrs={
                    'class': 'form-control'
                    }
                ),
            'description': forms.Textarea(
                attrs={
                    'class': 'form-control'
                    }
                ),
            'starting_bid': forms.NumberInput(
                attrs={
                    'class': 'form-control',
                    'Placeholder': '0.00',
                    }
                ),
            'categories':forms.CheckboxSelectMultiple(),
            'image_url': forms.TextInput(
                attrs={
                    'class': 'form-control'
                    }
                ),
            }

def index(request):
    listings=Listing.objects.exclude(active=False).all().order_by("-date")
    # to display the appropriate price
    for l in listings:
        l.starting_bid = get_bid(l)
    return render(request, "auctions/index.html",{
        "listings":listings
    })


def login_view(request):
    if request.method == "POST":

        # Attempt to sign user in
        username = request.POST["username"]
        password = request.POST["password"]
        user = authenticate(request, username=username, password=password)

        # Check if authentication successful
        if user is not None:
            login(request, user)
            return HttpResponseRedirect(reverse("index"))
        else:
            return render(request, "auctions/login.html", {
                "message": "Invalid username and/or password."
            })
    else:
        return render(request, "auctions/login.html")


def logout_view(request):
    logout(request)
    return HttpResponseRedirect(reverse("index"))


def register(request):
    if request.method == "POST":
        # validate data, 3 length max for all fiels
        for k in request.POST:
            if len(request.POST[k]) < 3:
                return render(request, "auctions/register.html", {
                "message": "Invalid data, Try again"
            })

        username = request.POST["username"]
        email = request.POST["email"]

        # Ensure password matches confirmation
        password = request.POST["password"]
        confirmation = request.POST["confirmation"]
        if password != confirmation:
            return render(request, "auctions/register.html", {
                "message": "Passwords must match."
            })

        # Attempt to create new user
        try:
            user = User.objects.create_user(username, email, password)
            user.save()
        except IntegrityError:
            return render(request, "auctions/register.html", {
                "message": "Username already taken."
            })
        login(request, user)
        return HttpResponseRedirect(reverse("index"))
    else:
        return render(request, "auctions/register.html")

@login_required(login_url='/login')
def create(request):
    new_listing=None
    message=""
    if request.method=="POST":
        new_listing_form=NewListingForm(data=request.POST)
        if new_listing_form.is_valid():
            new_listing=new_listing_form.save(commit=False)
            new_listing.owner=User.objects.get(pk=request.user.id)
            new_listing.save()
            # add selected categories to the listing, if any
            new_listing_form.save_m2m()
            return HttpResponseRedirect(reverse("listing", args=(new_listing.id,)))
        else:
            message="Error, Invalid data"
    else:
        new_listing=NewListingForm()
    return render(request, "auctions/create.html",{
        "form" : NewListingForm(),
        "message":message
    })

def listing(request, id):
    # ensure the requested listing is available, otherwise redirect to the active listings
    if Listing.objects.filter(pk=id).exists():
        listing = Listing.objects.get(pk=id)
    else:
        return HttpResponseRedirect(reverse("index"))

    current_bid = get_bid(listing)
    message={"type":None,"message":None}
    watchlist_action = None
    comments = listing.comment_set.all().order_by("-date")
    can_comment = False
    bid_message=""
    if request.user.is_authenticated:
        user=request.user
        can_comment = True
        watchlist_action=0
        if user.watchlists.filter(listing=listing).exists():
            watchlist_action=1
        # Handle forms data
        if request.POST.get('bid') and listing.active==True:
            user_bid=float(request.POST["bid"])
            if not user.bids.filter(listing=listing).exists():
                if user_bid > current_bid:
                    Bid.objects.create(listing=listing, bidder=user, bid=user_bid)
                    # before user refresh the page
                    current_bid=user_bid
                    message={"type":"success", "message" : "placed!"}
                else:
                    message={"type":"danger", "message" : f"Error! your bid must be greater than ${current_bid}"}
            else:
                if user_bid > current_bid:
                    bid = user.bids.get(listing=listing)
                    bid.bid=user_bid
                    bid.save()
                    # before user refresh the page
                    current_bid = user_bid
                    message={"type":"success", "message": "updated!"}
                else:
                    message={"type":"danger", "message": f"Error! your bid must be greater than ${current_bid}"}
        
        if request.GET.get('close')=="true":
            if listing.owner==request.user:
                listing.active=False
                if listing.bid_set.all().count()>0:
                    listing.winner=listing.bid_set.get(bid=current_bid).bidder
                listing.save()
            return HttpResponseRedirect(reverse("listing", args=(listing.id,)))

        if request.POST.get('comment'):
            comment=request.POST["comment"]
            user.comment_set.create(listing=listing, comment=comment)
            return HttpResponseRedirect(reverse("listing", args=(listing.id,)))

        if user.bids.filter(listing=listing).exists():
            bid_message = "Update Your Bid"
        else:
            bid_message = "Place Bid"
    
    return render(request, "auctions/listing.html",{
       "listing":listing,
       "current_bids_n": listing.bid_set.all().count(),
       "current_bid": current_bid,
       "comments": comments,
       "message_type":message["type"],
       "message":message["message"],
       "categories": listing.categories.all(),
       "can_comment": can_comment,
       "watchlist_action":watchlist_action,
       "bid_message":bid_message
    })

@login_required(login_url='/login')
def watchlist(request):
    user=User.objects.get(id=request.user.id)
    if request.GET.get('list') and request.GET.get('action'):
        list_id = int(request.GET['list'])
        action = request.GET['action']
        try:
            # try to get all user watchlists
            w = user.watchlists.filter(listing=Listing.objects.get(id=list_id))
            if action =="add" and w.count()==0:
                user.watchlists.create(listing=Listing.objects.get(id=list_id))
            elif action=="remove" and w.count()==1:
                    w.delete()
            return HttpResponseRedirect(reverse('listing', args=[list_id,]))
        except:
            return HttpResponseRedirect(reverse('index'))
    watchlist = Watchlist.objects.filter(user=user)
    return render(request, "auctions/watchlist.html",{
        "watchlist":watchlist
    })

def categories(request):
    categories = Category.objects.all()
    return render(request, "auctions/categories.html",{
        "categories":categories
    })

def category(request, category):
    try:
        category = Category.objects.get(category=category)
    except:
        return HttpResponseRedirect(reverse('categories'))
    listings=category.listing_set.exclude(active=False).all().order_by("-date")
    # to display the appropriate price
    for l in listings:
        l.starting_bid = get_bid(l)
    return render(request, "auctions/index.html",{
        "listings":listings,
        "category":category
    })

def get_bid(listing):
    '''
    this function return the maximum bid available, otherwise starting bid
    '''
    current_bids = listing.bid_set.all()
    price = listing.starting_bid
    if current_bids.count()>0:
        # get the highest bid, but don't save/change starting bid
        highest_bid=current_bids.aggregate(Max('bid'))["bid__max"]
        price = highest_bid
    return price