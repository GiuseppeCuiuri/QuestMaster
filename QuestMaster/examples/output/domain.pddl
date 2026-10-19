;; Quest Domain - Auto-generated
(define (domain quest-domain)
  (:requirements :strips :typing :action-costs)
  (:types agent location item obstacle - object)

  (:predicates
    (at ?a - agent ?l - location)
    (item_at ?i - item ?l - location)
    (has ?a - agent ?i - item)
    (connected ?l1 ?l2 - location)
    (clear ?l - location)
    (guarded_by ?l - location ?o - obstacle)
    (defeats ?i - item ?o - obstacle)
    (defeated ?o - obstacle)
  )

  (:functions (total-cost) - number)

  ;; The hero travels along a road to a place that nothing guards any more
  (:action move
    :parameters (?a - agent ?from ?to - location)
    :precondition (and (at ?a ?from) (connected ?from ?to) (clear ?to))
    :effect (and (not (at ?a ?from)) (at ?a ?to) (increase (total-cost) 1))
  )

  ;; The hero claims a treasure found where they stand
  (:action take
    :parameters (?a - agent ?i - item ?l - location)
    :precondition (and (at ?a ?l) (item_at ?i ?l))
    :effect (and (has ?a ?i) (not (item_at ?i ?l)) (increase (total-cost) 1))
  )

  ;; From the threshold, the hero turns the right treasure against the guardian of the next place
  (:action defeat_obstacle
    :parameters (?a - agent ?o - obstacle ?i - item ?from ?to - location)
    :precondition (and (at ?a ?from) (connected ?from ?to) (guarded_by ?to ?o)
                       (has ?a ?i) (defeats ?i ?o))
    :effect (and (defeated ?o) (clear ?to) (not (guarded_by ?to ?o)) (increase (total-cost) 1))
  )
)